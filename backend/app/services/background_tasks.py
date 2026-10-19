import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.models.command import Command
from app.models.device import Device
from app.services.command_dispatch import dispatch_command
from app.services.websocket_manager import manager


logger = logging.getLogger(__name__)
COMMAND_TIMEOUT_SECONDS = settings.COMMAND_TIMEOUT_SECONDS
HEARTBEAT_TIMEOUT_SECONDS = 60


def expire_commands(session, now):
    commands = session.exec(select(Command).where(
        Command.status.in_(["PENDING", "SENT", "ACKNOWLEDGED"]),
        (Command.ack_status.is_(None)) | (Command.ack_status != "COMPLETED"),
        Command.created_at <= now - timedelta(seconds=COMMAND_TIMEOUT_SECONDS),
    ).with_for_update(skip_locked=True)).all()
    events = []
    for command in commands:
        if command.ack_status == "COMPLETED":
            continue
        command.status = "TIMEOUT"
        unknown = any(child.get("dispatch_state") == "PUBLISHING" for child in (command.dispatches or {}).values())
        command.error_message = "Delivery unknown after interrupted publish" if unknown else "No completed ACK before timeout"
        session.add(command)
        events.append({"type": "command.updated", "data": {
            "request_id": command.request_id, "device_id": command.device_id,
            "status": "TIMEOUT", "error_message": command.error_message,
        }})
    session.commit()
    return events


def run_once():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as session:
        events = expire_commands(session, now)
        queued = session.exec(select(Command).where(Command.status.in_(["PENDING", "SENT", "ACKNOWLEDGED"]),
                              (Command.ack_status.is_(None)) | (Command.ack_status != "COMPLETED"))
                              .order_by(Command.created_at).limit(100)).all()
        for command in queued:
            if any(child.get("dispatch_state") == "QUEUED" for child in (command.dispatches or {}).values()):
                result = dispatch_command(session, command.id)
                events.append({"type": "command.updated", "data": {
                    "request_id": result.request_id, "device_id": result.device_id,
                    "action": result.action, "status": result.status, "ack_status": result.ack_status,
                    "error_message": result.error_message,
                }})
        devices = session.exec(select(Device).where(Device.status == "ONLINE",
            Device.last_seen <= now - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS))).all()
        for device in devices:
            device.status = "OFFLINE"
            session.add(device)
            events.append({"type": "device.updated", "data": {
                "device_id": device.id, "device_code": device.device_code, "status": "OFFLINE",
                "last_seen": device.last_seen.isoformat() + "Z" if device.last_seen else None,
            }})
        session.commit()
    for event in events:
        manager.send_from_thread(event)


def run_background_tasks(stop_event=None):
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        try:
            run_once()
        except Exception:
            logger.exception("Background task failed")
        stop_event.wait(1)
