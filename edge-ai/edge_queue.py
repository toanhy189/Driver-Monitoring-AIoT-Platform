
import sqlite3
import logging
import time
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS video_upload_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL UNIQUE,
                    video_path TEXT NOT NULL,
                    device_code TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0
                )
            """)
            queue_columns = {row[1] for row in conn.execute("PRAGMA table_info(offline_queue)")}
            for name, definition in (("next_attempt_at", "REAL NOT NULL DEFAULT 0"),
                                     ("backfill", "INTEGER NOT NULL DEFAULT 1"),
                                     ("last_error", "TEXT")):
                if name not in queue_columns:
                    conn.execute(f"ALTER TABLE offline_queue ADD COLUMN {name} {definition}")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(video_upload_queue)")}
            if "next_attempt_at" not in columns:
                conn.execute("ALTER TABLE video_upload_queue ADD COLUMN next_attempt_at REAL NOT NULL DEFAULT 0")
        logger.info("SQLite database initialized.")
        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to initialize SQLite database.")
        return False


def add_to_queue(message_id, topic, payload, backfill=True):
    """Lưu message vào hàng đợi."""
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT topic, payload FROM offline_queue WHERE message_id = ?",
                               (message_id,)).fetchone()
            if old is not None:
                return old == (topic, payload)
            count, used = conn.execute("SELECT COUNT(*), COALESCE(SUM(length(CAST(payload AS BLOB))), 0) "
                                       "FROM offline_queue").fetchone()
            maximum = int(os.getenv("AI_QUEUE_MAX_ROWS", "20000"))
            byte_limit = int(os.getenv("AI_QUEUE_MAX_PAYLOAD_BYTES", "67108864"))
            row_limit = maximum if topic.endswith("/events") else int(maximum * 0.9)
            if count >= row_limit or used + len(payload.encode("utf-8")) > byte_limit:
                logger.error("MQTT queue capacity reached; refusing message %s (no data deleted)", message_id)
                return False
            conn.execute("""
                INSERT OR IGNORE INTO offline_queue
                    (message_id, topic, payload, created_at, backfill)
                VALUES (?, ?, ?, ?, ?)
            """, (message_id, topic, payload, created_at, int(backfill)))

        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to add message to offline queue.")
        return False

def get_queue(limit=100, backfill=None):
    """Lấy các message đang chờ gửi, theo thứ tự thêm vào."""
    try:
        with get_connection() as conn:
            cursor = conn.execute("""
                SELECT message_id, topic, payload, created_at, retry_count, backfill
                FROM offline_queue
                WHERE status = 'PENDING' AND next_attempt_at <= ?
                    AND (? IS NULL OR backfill = ?)
                ORDER BY backfill ASC,
                    CASE WHEN backfill = 0 AND topic LIKE '%/events' THEN 0 ELSE 1 END,
                    id ASC
                LIMIT ?
            """, (time.time(), backfill, backfill, limit))

            return cursor.fetchall()

    except (sqlite3.Error, OSError):
        logger.exception("Failed to retrieve offline queue.")
        return None


def mark_backfill():
    with get_connection() as conn:
        conn.execute("UPDATE offline_queue SET backfill = 1 WHERE status = 'PENDING'")


def schedule_message(message_id, delay, error=None, attempted=False, dead=False):
    with get_connection() as conn:
        conn.execute("UPDATE offline_queue SET next_attempt_at = ?, last_error = ?, "
                     "retry_count = retry_count + ?, status = ? WHERE message_id = ?",
                     (time.time() + delay, error, int(attempted), "DEAD" if dead else "PENDING", message_id))

def remove_from_queue(message_ids):
    """Xóa các message đã được xác nhận xử lý thành công."""
    if not message_ids:
        return True

    try:
        with get_connection() as conn:
            for message_id in message_ids:
                cursor = conn.execute(
                    """
                    DELETE FROM offline_queue
                    WHERE message_id = ?
                    """,
                    (message_id,),
                )

                if cursor.rowcount > 0:
                    logger.info(
                        "Removed message %s from offline queue.",
                        message_id,
                    )
                else:
                    logger.warning(
                        "Message %s was not found in offline queue.",
                        message_id,
                    )

        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to remove messages from offline queue.")
        return False


# Lưu video vào hàng đợi
def add_video_to_queue(video_id, video_path, device_code, state):
    """Đăng ký video đã ghi xong vào hàng đợi upload."""
    created_at = datetime.now(timezone.utc).isoformat()
    video_path = str(Path(video_path).resolve())

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO video_upload_queue (
                    video_id, video_path, device_code,
                    state, created_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                video_id, video_path, device_code,
                state, created_at
            ))
            stored = conn.execute("""
                SELECT video_path, device_code, state FROM video_upload_queue WHERE video_id = ?
            """, (video_id,)).fetchone()
            if stored != (video_path, device_code, state):
                logger.error("Video ID reused with different metadata: %s", video_id)
                return False

        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to enqueue video.")
        return False


def get_pending_videos(limit=5):
    """Lấy video đang chờ upload."""
    try:
        with get_connection() as conn:
            return conn.execute("""
                SELECT video_id, video_path, device_code, state,
                       status, retry_count
                FROM video_upload_queue
                WHERE status IN ('PENDING', 'UPLOADED')
                    AND next_attempt_at <= ?
                ORDER BY CASE WHEN status = 'UPLOADED' THEN 0 ELSE 1 END, id ASC
                LIMIT ?
            """, (time.time(), limit)).fetchall()

    except (sqlite3.Error, OSError):
        logger.exception("Failed to retrieve video queue.")
        return None


def update_video_status(video_id, status, increment_retry=False, next_attempt_at=0):
    """Cập nhật trạng thái và số lần thử upload."""
    try:
        with get_connection() as conn:
            if increment_retry:
                conn.execute("""
                    UPDATE video_upload_queue
                    SET retry_count = retry_count + 1
                    WHERE video_id = ?
                """, (video_id,))

            conn.execute("""
                UPDATE video_upload_queue
                SET status = ?, next_attempt_at = ?
                WHERE video_id = ?
            """, (status, next_attempt_at, video_id))

        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to update video status.")
        return False


def remove_video_from_queue(video_id):
    """Xóa video khỏi hàng đợi sau khi hoàn tất xử lý."""
    try:
        with get_connection() as conn:
            conn.execute("""
                DELETE FROM video_upload_queue
                WHERE video_id = ?
            """, (video_id,))

        logger.info(f"Video {video_id} removed from queue.")
        return True

    except (sqlite3.Error, OSError):
        logger.exception("Failed to remove video from queue.")
        return False
