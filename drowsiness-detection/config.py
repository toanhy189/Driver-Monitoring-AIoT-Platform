import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEVICE_ID = "vision-01"

MQTT_BROKER = os.getenv("AI_MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

MQTT_TOPIC = "driver/telemetry"

EAR_THRESHOLD = 0.20
PERCLOS_THRESHOLD = 0.20

# Tuần 2
MQTT_EVENT_TOPIC = "driver/events"
MODEL_VERSION = "drowsiness-v1.0"

MQTT_STATUS_TOPIC = "driver/status"
MQTT_USERNAME = os.getenv("AI_MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("AI_MQTT_PASSWORD") or None
