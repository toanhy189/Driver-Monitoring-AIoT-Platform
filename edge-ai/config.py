import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")

TASK_PATH = BASE_DIR / "face_landmarker.task"
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("AI_QUEUE_DB", str(DATA_DIR / "queue.db")))


MQTT_BROKER = os.getenv("AI_MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("AI_MQTT_PORT", os.getenv("MQTT_PORT", "1883")))

MQTT_USERNAME = os.getenv("AI_MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("AI_MQTT_PASSWORD") or None

DEVICE_CODE = os.getenv("AI_DEVICE_CODE", "vision-01")
MODEL_VERSION = "drowsiness-v3.0"

STATUS_TOPIC = f"driver/{DEVICE_CODE}/status"
TELEMETRY_TOPIC = f"driver/{DEVICE_CODE}/telemetry"
EVENT_TOPIC = f"driver/{DEVICE_CODE}/events"
ACK_TOPIC = f"driver/{DEVICE_CODE}/storage_ack"

EAR_THRESHOLD = 0.20
PERCLOS_THRESHOLD = 0.20
