"""Persist intent before MQTT. Ambiguous sends are never retried automatically."""

from datetime import datetime, timezone
from time import perf_counter

from sqlmodel import Session, select

from app.models.command import Command
from app.models.command_type import CommandType
from app.models.device import Device
from app.services.command_service import publish_command
from app.services.command_state import aggregate, update_dispatch


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_command(session: Session, device: Device, action: str, actions: dict,
                   user_id: int | None = None, alert_id: int | None = None,
                   idempotency_key: str | None = None, request_hash: str | None = None) -> Command:
    kind = session.exec(select(CommandType).where(CommandType.code == action)).first()
    if kind is None:
        raise RuntimeError(f"Command type {action} missing; run migration")
    command = Command(device_id=device.id, command_type_id=kind.id, action=action,
                      created_by_user_id=user_id, alert_id=alert_id, status="PENDING",
                      idempotency_key=idempotency_key, request_hash=request_hash)
    session.add(command)
    session.flush()
    command.request_id = f"cmd-{command.id}"
    command.dispatches = {key: {
        "request_id": f"cmd-{command.id}-{key}", "status": "PENDING",
        "dispatch_state": "QUEUED", "payload": parameters,
    } for key, parameters in actions.items()}
    session.add(command)
    return command


def dispatch_command(session: Session, command_id: int, publisher=None) -> Command | None:
    publisher = publisher or publish_command
    command = session.get(Command, command_id)
    if command is None:
        return None
    for key in list(command.dispatches or {}):
        command = session.exec(select(Command).where(Command.id == command_id)
                               .with_for_update().execution_options(populate_existing=True)).one()
        child = (command.dispatches or {}).get(key, {})
        if child.get("dispatch_state") != "QUEUED" or command.status in {"FAILED", "TIMEOUT"}:
            session.commit()
            continue
        device = session.exec(select(Device).where(Device.id == command.device_id).with_for_update()).one()
        fresh = device.last_seen and -5 <= (now() - device.last_seen).total_seconds() <= 90
        if device.lifecycle_state != "ACTIVE" or device.status != "ONLINE" or not fresh:
            command.dispatches = update_dispatch(command.dispatches, key, "FAILED", "Device is not active and online")
            aggregate(command)
            session.add(command)
            session.commit()
            continue
        started = now()
        command.dispatches = {**command.dispatches, key: {
            **child, "dispatch_state": "PUBLISHING", "publish_started_at": started.isoformat() + "Z",
        }}
        session.add(command)
        session.commit()  # A crash after this point has unknown delivery: no automatic resend.
        timer = perf_counter()
        success = publisher(device.device_code, {"request_id": child["request_id"], **child["payload"]})
        duration = round((perf_counter() - timer) * 1000, 3)
        command = session.exec(select(Command).where(Command.id == command_id)
                               .with_for_update().execution_options(populate_existing=True)).one()
        command.dispatches = update_dispatch(command.dispatches, key, "SENT" if success else "FAILED",
                                               None if success else "MQTT publish failed")
        command.dispatches = {**command.dispatches, key: {
            **command.dispatches[key], "dispatch_state": "PUBLISHED" if success else "PUBLISH_FAILED",
            "publish_ms": duration, "published_at": now().isoformat() + "Z" if success else None,
        }}
        if success:
            command.mqtt_published_at = now()
        if command.status != "TIMEOUT":
            aggregate(command)
        session.add(command)
        session.commit()
    return command
