import json
import uuid

from edge_queue import add_to_queue
import logging

from config import DEVICE_CODE, EVENT_TOPIC, MODEL_VERSION, TELEMETRY_TOPIC, EVENT_AUDIT_PATH
from service.utils import current_timestamp

logger = logging.getLogger(__name__)

def send_message(mqtt_client, topic, data):
    """Lưu message trước, sau đó thử gửi qua MQTT."""
    message_id = data.get("message_id") or str(uuid.uuid4())
    data = {**data, "message_id": message_id}
    data.setdefault("model_version", getattr(mqtt_client, "model_version", MODEL_VERSION))

    payload = json.dumps(data, allow_nan=False, sort_keys=True, separators=(",", ":"))

    print("=====================================================", flush=True)
    print(f"[MQTT] Queueing message for topic '{topic}':\n{payload}", flush=True)
    print("=====================================================", flush=True)
    
    # Lưu vào SQLite trước khi gửi
    if not add_to_queue(message_id, topic, payload, backfill=not mqtt_client.connected):
        logger.error("Message was not saved; skipping publish")
        return False

    mqtt_client.notify_queue()
    if topic.endswith("/events"):
        try:
            EVENT_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            if EVENT_AUDIT_PATH.exists() and EVENT_AUDIT_PATH.stat().st_size > 5*1024*1024:
                EVENT_AUDIT_PATH.replace(EVENT_AUDIT_PATH.with_suffix(".previous.jsonl"))
            with EVENT_AUDIT_PATH.open("a", encoding="utf-8") as audit:
                audit.write(payload+"\n")
        except OSError:
            logger.exception("Cannot write local event audit; durable outbox remains available")
    return True  # Durable enqueue, not a broker or backend acknowledgement.


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
        "model_version": state_data.get("model_version", MODEL_VERSION),
        "timestamp": current_timestamp(),
        "session_id": state_data.get("session_id"),
        "episode_id": state_data.get("episode_id"),
        "observed_at": state_data.get("observed_at"),
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
