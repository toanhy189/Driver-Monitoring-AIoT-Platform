
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from config import DB_PATH

# Cấu hình logging
logger = logging.getLogger(__name__)

@contextmanager
def get_connection():
    """Mở connection, quản lý transaction và luôn đóng connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)

    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """Khởi tạo database và bảng hàng đợi."""
    try:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS offline_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    retry_count INTEGER NOT NULL DEFAULT 0
                )
            """)
        logger.info("SQLite database initialized.")
        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to initialize SQLite database.")
        return False


def add_to_queue(message_id, topic, payload):
    """Lưu message vào hàng đợi."""
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO offline_queue
                    (message_id, topic, payload, created_at)
                VALUES (?, ?, ?, ?)
            """, (message_id, topic, payload, created_at))

        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to add message to offline queue.")
        return False

def get_queue(limit=100):
    """Lấy các message đang chờ gửi, theo thứ tự thêm vào."""
    try:
        with get_connection() as conn:
            cursor = conn.execute("""
                SELECT message_id, topic, payload, created_at
                FROM offline_queue
                WHERE status = 'PENDING'
                ORDER BY id ASC
                LIMIT ?
            """, (limit,))

            return cursor.fetchall()

    except (sqlite3.Error, OSError):
        logger.exception("Failed to retrieve offline queue.")
        return None

def remove_from_queue(message_ids):
    """Xóa các message đã được xác nhận xử lý thành công."""
    if not message_ids:
        return True

    try:
        with get_connection() as conn:
            conn.executemany("""
                DELETE FROM offline_queue
                WHERE message_id = ?
            """, [(message_id,) for message_id in message_ids])

        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to remove messages from offline queue.")
        return False
