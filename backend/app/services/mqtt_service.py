"""Translate existing AI and ESP32 MQTT messages into database snapshots and FE events."""

import hashlib
import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models.alert import Alert
from app.models.ai_event import AiEvent, AiMessageReceipt
from app.models.command import Command
from app.models.config import Config
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.schemas.ai_telemetry import QueuedTelemetry
from app.schemas.rules import AiEventRequest
from app.services.command_state import aggregate, update_dispatch
from app.services.websocket_manager import manager


logger = logging.getLogger(__name__)

# Edge AI uses driver/{code}/{telemetry,events,status}; legacy shared topics remain accepted.
# ESP32 currently uses driver/{code}/status and driver/{code}/ack.
TOPICS = [("driver/#", 1)]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _timestamp(value) -> datetime:
    if not isinstance(value, str):
        return _now()
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            return result
        return result.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return _now()


def _device(session: Session, code: str | None) -> Device | None:
    if not isinstance(code, str) or not code:
        return None
    return session.exec(select(Device).where(Device.device_code == code)).first()


def _device_event(device: Device) -> dict:
    return {
        "type": "device.updated",
        "data": {
            "device_id": device.id,
            "device_code": device.device_code,
            "status": device.status,
            "last_seen": device.last_seen.isoformat() + "Z" if device.last_seen else None,
            "firmware_version": device.firmware_version,
        },
    }


def _save_telemetry(session: Session, code: str, payload: dict, *, commit: bool = True) -> list[dict]:
    device = _device(session, code)
    if device is None or device.lifecycle_state == "DECOMMISSIONED":
        return []
    pose = payload.get("head_pose")
    pose = pose if isinstance(pose, dict) else None
    telemetry = Telemetry(
        device_id=device.id,
        recorded_at=_timestamp(payload.get("timestamp")),
        ear=payload.get("ear"),
        perclos=payload.get("perclos"),
        driver_state=payload.get("driver_state"),
        face_detected=payload.get("face_detected") if type(payload.get("face_detected")) is bool else None,
        head_pose=pose,
        angle_x=payload.get("angle_x"),
        angle_y=payload.get("angle_y"),
        angle_z=payload.get("angle_z"),
        confidence=payload.get("confidence"),
        model_version=payload.get("model_version"),
    )
    session.add(telemetry)
    device.status = "ONLINE"
    device.last_seen = _now()
    session.add(device)
    session.commit() if commit else session.flush()
    return [
        {
            "type": "telemetry.updated",
            "data": {
                "id": telemetry.id,
                "device_id": device.id,
                "device_code": device.device_code,
                "recorded_at": telemetry.recorded_at.isoformat() + "Z",
                "ear": telemetry.ear,
                "perclos": telemetry.perclos,
                "driver_state": telemetry.driver_state,
                "face_detected": telemetry.face_detected,
                "head_pose": telemetry.head_pose,
                "confidence": telemetry.confidence,
                "model_version": telemetry.model_version,
                "angle_x": telemetry.angle_x, "angle_y": telemetry.angle_y, "angle_z": telemetry.angle_z,
            },
        },
        _device_event(device),
    ]


def _save_status(session: Session, code: str, payload: dict) -> list[dict]:
    device = _device(session, code)
    if device is None or device.lifecycle_state == "DECOMMISSIONED":
        return []
    state = payload.get("status")
    if state not in {"ONLINE", "ALIVE", "OFFLINE"}:
        return []
    device.status = "ONLINE" if state in {"ONLINE", "ALIVE"} else "OFFLINE"
    if device.status == "ONLINE":
        device.last_seen = _now()
    firmware = payload.get("firmware_version")
    if isinstance(firmware, str) and firmware:
        device.firmware_version = firmware[:80]
    session.add(device)
    session.commit()
    return [_device_event(device)]


def _save_ai_event(session: Session, payload: dict) -> list[dict]:
    from app.services.rule_engine import process_event
    return process_event(session, payload)


def _save_queued_ai(session: Session, code: str, topic: str, kind: str, payload: dict) -> list[dict]:
    """One transaction saves data and its receipt; a retry only repeats the acknowledgement."""
    from app.services.rule_engine import event_payload_hash, process_event

    message_id = payload.get("message_id")
    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 80:
        return []
    source = session.exec(select(Device).where(Device.device_code == code).with_for_update()).first()
    if source is None or source.device_type != "VISION_NODE" or source.lifecycle_state == "DECOMMISSIONED":
        return []
    try:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError):
        return []
    saved = session.exec(select(AiMessageReceipt).where(
        AiMessageReceipt.device_id == source.id, AiMessageReceipt.message_id == message_id)).first()
    acknowledgement = {"type": "ingest.saved", "data": {"device_code": code, "message_id": message_id}}
    if saved:
        if saved.topic != topic or saved.payload_hash != digest:
            logger.warning("Ignoring reused AI message ID with different content")
            return []
        return [acknowledgement]
    try:
        if kind == "telemetry":
            data = QueuedTelemetry.model_validate(payload)
            latest = session.exec(select(Telemetry.recorded_at).where(Telemetry.device_id == source.id)
                                  .order_by(Telemetry.recorded_at.desc()).limit(1)).first()
            events = _save_telemetry(session, code, data.model_dump(mode="json"), commit=False)
            if latest and data.timestamp.astimezone(timezone.utc).replace(tzinfo=None) < latest:
                events = [event for event in events if event["type"] != "telemetry.updated"]
        else:
            data = AiEventRequest.model_validate(payload)
            events = process_event(session, payload, commit=False)
            event = session.exec(select(AiEvent).where(AiEvent.event_id == data.event_id)).first()
            if event is None or event.device_id != source.id or event.payload_hash != event_payload_hash(payload, data):
                session.rollback()
                return []
    except ValidationError:
        session.rollback()
        logger.warning("Ignoring invalid queued AI message")
        return []
    session.add(AiMessageReceipt(device_id=source.id, message_id=message_id, topic=topic, payload_hash=digest))
    session.commit()  # Must succeed before the MQTT callback can publish SAVED.
    return [*events, acknowledgement]


def _save_ack(session: Session, code: str, payload: dict) -> list[dict]:
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id.startswith("cmd-"):
        return []
    parts = request_id.split("-", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        return []
    command = session.exec(
        select(Command).where(Command.id == int(parts[1])).with_for_update()
    ).first()
    if command is None or not command.dispatches:
        return []
    device = session.get(Device, command.device_id)
    if device is None or device.device_code != code:
        return []
    key = parts[2]
    if key not in command.dispatches or command.dispatches[key]["request_id"] != request_id:
        return []
    state = payload.get("status")
    if state not in {"ACKNOWLEDGED", "STARTED", "COMPLETED", "FAILED", "INTERRUPTED"}:
        return []
    if command.status == "TIMEOUT" and state in {"ACKNOWLEDGED", "STARTED"}:
        return []
    was_timeout = command.status == "TIMEOUT"
    previous_ack_status = command.ack_status
    previous_error = command.error_message
    previous = command.dispatches[key]["status"]
    command.dispatches = update_dispatch(
        command.dispatches, key,
        "FAILED" if state == "INTERRUPTED" else state,
        payload.get("error") or ("Command interrupted" if state == "INTERRUPTED" else None),
    )
    if command.dispatches[key]["status"] == previous:
        return []
    received = _now()
    child = command.dispatches[key]
    command.dispatches = {**command.dispatches, key: {
        **child, "first_ack_at": child.get("first_ack_at") or received.isoformat() + "Z",
        **({"completed_ack_at": received.isoformat() + "Z"} if state == "COMPLETED" else {}),
    }}
    if command.first_ack_at is None:
        command.first_ack_at = received
    aggregate(command)
    if command.ack_status == "COMPLETED":
        command.completed_ack_at = received
    # A single late child ACK does not resolve the whole timed-out request.
    if was_timeout and command.status == "ACKNOWLEDGED" and command.ack_status != "COMPLETED":
        command.status = "TIMEOUT"
        command.ack_status = previous_ack_status
        command.error_message = previous_error
    session.add(command)
    session.commit()
    return [{"type": "command.updated", "data": {
        "request_id": command.request_id,
        "device_id": device.id,
        "device_code": device.device_code,
        "action": command.action,
        "status": command.status,
        "ack_status": command.ack_status,
        "error_message": command.error_message,
    }}]


def _save_applied_config(session: Session, code: str, payload: dict) -> list[dict]:
    device = _device(session, code)
    if device is None or device.lifecycle_state == "DECOMMISSIONED":
        return []
    if payload.get("device_code") != code:
        return []
    config = session.exec(select(Config).where(Config.device_id == device.id).with_for_update()).first()
    desired = config.desired_config if config else None
    if (not isinstance(desired, dict) or not desired.get("config_id") or
            "timings" not in desired or payload.get("config_id") != desired.get("config_id")):
        return []
    status = payload.get("status")
    if status not in {"APPLIED", "REJECTED"}:
        return []
    if status == "APPLIED":
        applied = {"config_id": desired["config_id"], "timings": desired["timings"]}
        if config.applied_config == applied and desired.get("status") == "APPLIED":
            return []
        config.applied_config = applied
        config.desired_config = {**desired, "status": "APPLIED", "error": None}
    else:
        if desired.get("status") == "APPLIED" and config.applied_config and \
                config.applied_config.get("config_id") == desired["config_id"]:
            return []
        reason = payload.get("error")
        reason = reason[:120] if isinstance(reason, str) and reason else "Device rejected configuration"
        if desired.get("status") == "REJECTED" and desired.get("error") == reason:
            return []
        config.desired_config = {**desired, "status": "REJECTED", "error": reason}
    config.updated_at = _now()
    session.add(config)
    session.commit()
    return [{"type": "config.updated", "data": {
        "device_id": device.id,
        "device_code": device.device_code,
        "config_id": desired["config_id"],
        "applied_config_id": config.applied_config.get("config_id") if config.applied_config else None,
        "status": status,
        "error": config.desired_config.get("error"),
    }}]


def process_message(topic: str, payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    parts = topic.split("/")
    if not parts or parts[0] != "driver":
        return []
    if len(parts) == 3:
        # The ACL protects the topic; reject an inconsistent source inside the JSON too.
        for field in ("device_code", "device_id"):
            if payload.get(field) is not None and payload[field] != parts[1]:
                return []
    with Session(engine) as session:
        if topic == "driver/telemetry":
            return _save_telemetry(session, payload.get("device_id"), payload)
        if topic == "driver/events":
            return _save_ai_event(session, payload)
        if topic == "driver/status":
            return _save_status(session, payload.get("device_id"), payload)
        if len(parts) == 3 and parts[2] == "telemetry":
            if "message_id" in payload:
                return _save_queued_ai(session, parts[1], topic, "telemetry", payload)
            return _save_telemetry(session, parts[1], payload)
        if len(parts) == 3 and parts[2] == "events":
            if "message_id" in payload:
                return _save_queued_ai(session, parts[1], topic, "events", payload)
            return _save_ai_event(session, payload)
        if len(parts) == 3 and parts[2] in {"status", "heartbeat"}:
            return _save_status(session, parts[1], payload)
        if len(parts) == 3 and parts[2] == "ack":
            return _save_ack(session, parts[1], payload)
        if len(parts) == 4 and parts[2:] == ["config", "applied"]:
            return _save_applied_config(session, parts[1], payload)
    return []


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe(TOPICS)


def on_message(client, userdata, msg):
    # These are BE output topics; retained tombstones are valid and need no JSON parsing.
    if msg.topic.endswith(("/command", "/config/update", "/storage_ack")):
        return
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        for event in process_message(msg.topic, payload):
            if event["type"] == "ingest.saved":
                data = event["data"]
                result = client.publish(f"driver/{data['device_code']}/storage_ack",
                    json.dumps({"message_id": data["message_id"], "status": "SAVED"}), qos=1, retain=False)
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    logger.warning("Storage ACK publish failed; the AI queue can retry the same message")
            else:
                manager.send_from_thread(event)
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Ignoring invalid MQTT JSON on %s", msg.topic)
    except Exception:
        logger.exception("Failed to process MQTT message on %s", msg.topic)


def start_mqtt_consumer(stop_event=None):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT, 60)
    if stop_event is None:
        client.loop_forever(retry_first_connection=True)
    else:
        client.loop_start()
        stop_event.wait()
        client.disconnect()
        client.loop_stop()
