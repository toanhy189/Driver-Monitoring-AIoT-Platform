import logging
import time
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.db import engine
from app.models.command import Command
from app.models.device import Device
from app.services.websocket_manager import manager


logger = logging.getLogger(__name__)
COMMAND_TIMEOUT_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 60


def run_background_tasks():
    while True:
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            with Session(engine) as session:
                commands = session.exec(
                    select(Command).where(
                        Command.status.in_(["PENDING", "SENT", "ACKNOWLEDGED"]),
                        Command.created_at <= now - timedelta(seconds=COMMAND_TIMEOUT_SECONDS),
                    )
                ).all()
                for command in commands:
                    if command.ack_status == "COMPLETED":
                        continue
                    command.status = "TIMEOUT"
                    command.error_message = "No completed ACK before timeout"
                    session.add(command)
                devices = session.exec(
                    select(Device).where(
                        Device.status == "ONLINE",
                        Device.last_seen <= now - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS),
                    )
                ).all()
                for device in devices:
                    device.status = "OFFLINE"
                    session.add(device)
                session.commit()
                for command in commands:
                    if command.status == "TIMEOUT":
                        manager.send_from_thread({"type": "command.updated", "data": {
                            "request_id": command.request_id or f"cmd-{command.id}",
                            "device_id": command.device_id,
                            "status": "TIMEOUT",
                            "error_message": command.error_message,
                        }})
                for device in devices:
                    manager.send_from_thread({"type": "device.updated", "data": {
                        "device_id": device.id,
                        "device_code": device.device_code,
                        "status": "OFFLINE",
                        "last_seen": device.last_seen.isoformat() + "Z" if device.last_seen else None,
                    }})
        except Exception:
            logger.exception("Background task failed")
        time.sleep(10)
