from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

TASK_PATH = BASE_DIR / "face_landmarker.task"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "edge_queue.db"


MQTT_BROKER = "localhost"
MQTT_PORT = 1883

MQTT_USERNAME = None
MQTT_PASSWORD = None

DEVICE_CODE = "vision-01"
MODEL_VERSION = "drowsiness-v3.0"

STATUS_TOPIC = "driver/vision-01/status"
TELEMETRY_TOPIC = "driver/vision-01/telemetry"
EVENT_TOPIC = "driver/vision-01/events"
ACK_TOPIC = "driver/vision-01/storage_ack"

EAR_THRESHOLD = 0.20
PERCLOS_THRESHOLD = 0.20






