import json
import uuid

from edge_queue import add_to_queue
import logging

from config import DEVICE_CODE, EVENT_TOPIC, MODEL_VERSION, TELEMETRY_TOPIC
from service.utils import current_timestamp

logger = logging.getLogger(__name__)

def send_message(mqtt_client, topic, data):
    """Lưu message trước, sau đó thử gửi qua MQTT."""
    message_id = data.get("message_id") or str(uuid.uuid4())
    data["message_id"] = message_id

    payload = json.dumps(data)

    print("=====================================================", flush=True)
    print(f"[MQTT] Sending message to topic '{topic}':\n{payload}", flush=True)
    print("=====================================================", flush=True)
    
    # Lưu vào SQLite trước khi gửi
    if not add_to_queue(message_id, topic, payload):
        logger.error("Message was not saved; skipping publish")
        return False

    # Nếu MQTT chưa kết nối, message vẫn nằm trong SQLite
    if not mqtt_client.connected:
        return False

    # Chỉ xóa message khi đã nhận ACK từ backend (xem mqtt_client)
    topicc = topic.split("/")[-1]
    if topicc == "telemetry":
        info = mqtt_client.publish_telemetry(data)
    elif topicc == "events":
        info = mqtt_client.publish_event(data)

    return info is not None and info.rc == 0


def publish_event(mqtt_client, event):
    """Gửi event lên MQTT."""
    if event is None:
        return

    try:
        send_message(mqtt_client, EVENT_TOPIC, event)

    except Exception as exc:
        print(f"[MQTT] Không gửi được event: {exc}")


def publish_telemetry(
    mqtt_client, state_data, face_detected,
    ear, perclos, eye_closed, pose,
):
    """Gửi telemetry định kỳ, kể cả khi không phát hiện khuôn mặt."""

    confirmed_state = state_data["confirmed_state"] or "UNKNOWN"

    head_pose_data = {
        "yaw": None,
        "pitch": None,
        "roll": None,
    }

    if pose is not None:
        head_pose_data = {
            "yaw": pose.get("yaw"),
            "pitch": pose.get("pitch"),
            "roll": pose.get("roll"),
        }

    payload = {
        "message_id": str(uuid.uuid4()),
        "device_code": DEVICE_CODE,
        "model_version": MODEL_VERSION,
        "timestamp": current_timestamp(),
        "driver_state": confirmed_state,
        "candidate_state": state_data["candidate_state"],
        "face_detected": face_detected,
        "ear": ear,
        "perclos": perclos,
        "eyes_closed": eye_closed,
        "head_pose": head_pose_data,
    }

    try:
        send_message(mqtt_client, TELEMETRY_TOPIC, payload)

    except Exception as exc:
        print(f"[MQTT] Không gửi được telemetry: {exc}")
