import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")

TASK_PATH = BASE_DIR / "face_landmarker.task"
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("AI_QUEUE_DB", str(DATA_DIR / "queue.db")))

# Cấu hình video
BACKEND_HOST = os.getenv("BACKEND_HOST", "http://localhost:8000")
API_STR = os.getenv("API_STR", "/api")

MQTT_BROKER = os.getenv("AI_MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("AI_MQTT_PORT", os.getenv("MQTT_PORT", "1883")))

MQTT_USERNAME = os.getenv("AI_MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("AI_MQTT_PASSWORD") or None

DEVICE_CODE = os.getenv("AI_DEVICE_CODE", "vision-01")
MODEL_VERSION = "drowsiness-v3.1-pixel"
AI_MODEL_MODE = os.getenv("AI_MODEL_MODE", "baseline").lower()
AI_MODEL_PATH = Path(os.getenv("AI_MODEL_PATH", str(BASE_DIR / "ml-runs" / "uta-optimized-v2" / "selected.joblib")))
if AI_MODEL_MODE not in {"baseline", "ml"}:
    raise ValueError("AI_MODEL_MODE must be baseline or ml")

STATUS_TOPIC = f"driver/{DEVICE_CODE}/status"
TELEMETRY_TOPIC = f"driver/{DEVICE_CODE}/telemetry"
EVENT_TOPIC = f"driver/{DEVICE_CODE}/events"
ACK_TOPIC = f"driver/{DEVICE_CODE}/storage_ack"

EAR_THRESHOLD = 0.20
PERCLOS_THRESHOLD = 0.20

# Observation gaps interrupt continuous timers. Values are adjustable demo defaults.
FACE_LOSS_RESET_SECONDS = float(os.getenv("AI_FACE_LOSS_RESET_SECONDS", "1.0"))
MAX_OBSERVATION_GAP_SECONDS = float(os.getenv("AI_MAX_OBSERVATION_GAP_SECONDS", "0.5"))
LOCAL_ALERT_ENABLED = os.getenv("AI_LOCAL_ALERT_ENABLED", "true").lower() in {"true", "1", "yes"}
LOCAL_ALERT_COOLDOWN_SECONDS = float(os.getenv("AI_LOCAL_ALERT_COOLDOWN_SECONDS", "10"))
VIDEO_UPLOAD_INTERVAL_SECONDS = float(os.getenv("AI_VIDEO_UPLOAD_INTERVAL_SECONDS", "5"))
VIDEO_UPLOAD_MAX_RETRY_SECONDS = float(os.getenv("AI_VIDEO_UPLOAD_MAX_RETRY_SECONDS", "300"))
RECORDING_DIR = Path(os.getenv("AI_RECORDING_DIR", str(BASE_DIR / "recordings")))
VIDEO_MAX_CLIP_SECONDS = float(os.getenv("AI_VIDEO_MAX_CLIP_SECONDS", "60"))
VIDEO_MAX_CLIP_BYTES = int(os.getenv("AI_VIDEO_MAX_CLIP_BYTES", "33554432"))
VIDEO_STORAGE_MAX_BYTES = int(os.getenv("AI_VIDEO_STORAGE_MAX_BYTES", "1073741824"))
METRICS_PATH = BASE_DIR / "data" / "performance.jsonl"
EVENT_AUDIT_PATH = Path(os.getenv("AI_EVENT_AUDIT_PATH", str(BASE_DIR / "data" / "events.jsonl")))

for _name in ("FACE_LOSS_RESET_SECONDS", "MAX_OBSERVATION_GAP_SECONDS",
              "VIDEO_UPLOAD_INTERVAL_SECONDS", "VIDEO_UPLOAD_MAX_RETRY_SECONDS", "VIDEO_MAX_CLIP_SECONDS",
              "VIDEO_MAX_CLIP_BYTES", "VIDEO_STORAGE_MAX_BYTES"):
    if not 0 < globals()[_name] < float("inf"):
        raise ValueError(f"{_name} must be a finite positive number")
if not 0 <= LOCAL_ALERT_COOLDOWN_SECONDS < float("inf"):
    raise ValueError("LOCAL_ALERT_COOLDOWN_SECONDS must be finite and nonnegative")
