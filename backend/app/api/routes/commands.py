from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import require_operator, require_viewer
from app.core.db import get_session
from app.models.command import Command
from app.models.command_type import CommandType
from app.models.device import Device
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.command import LegacyCommandRequest, TestAlertRequest
from app.services.access import assigned_device
from app.services.audit_service import log_action
from app.services.command_service import publish_command
from app.services.command_state import aggregate, update_dispatch
from app.services.time_utils import as_utc


router = APIRouter(tags=["commands"])


def _command_type(session: Session, code: str) -> CommandType:
    item = session.exec(select(CommandType).where(CommandType.code == code)).first()
    if item is None:
        raise HTTPException(status_code=503, detail=f"Command type {code} is missing; run migration")
    return item


def _fresh(last_seen: datetime | None) -> bool:
    if last_seen is None:
        return False
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - last_seen
    return timedelta(seconds=-5) <= age <= timedelta(seconds=90)


def _public(session: Session, command: Command, device: Device | None = None) -> dict:
    device = device or session.get(Device, command.device_id)
    creator = session.get(User, command.created_by_user_id) if command.created_by_user_id else None
    command_type = session.get(CommandType, command.command_type_id)
    status = command.status
    ack_status = command.ack_status
    if status == "EXECUTED":
        status, ack_status = "ACKNOWLEDGED", "COMPLETED"
    return {
        "request_id": command.request_id or f"cmd-{command.id}",
        "device_id": command.device_id,
        "device_code": device.device_code if device else None,
        "action": command.action or (command_type.code if command_type else None),
        "created_by_name": creator.fullname if creator else None,
        "created_at": as_utc(command.created_at),
        "status": status,
        "ack_status": ack_status,
        "error_message": command.error_message,
        "executed_at": as_utc(command.executed_at),
    }


def _save_parent(
    session: Session, device: Device, user: User, action: str,
    dispatches: dict,
) -> Command:
    command_type = _command_type(session, action)
    parent = Command(
        device_id=device.id,
        command_type_id=command_type.id,
        action=action,
        created_by_user_id=user.id,
        status="PENDING",
    )
    session.add(parent)
    session.flush()
    parent.request_id = f"cmd-{parent.id}"
    parent.dispatches = {
        key: {"request_id": f"cmd-{parent.id}-{key}", "status": "PENDING"}
        for key in dispatches
    }
    session.add(parent)
    session.commit()
    return parent


def _publish_actions(session: Session, parent: Command, device: Device, actions: dict) -> dict:
    for key, parameters in actions.items():
        child_request_id = parent.dispatches[key]["request_id"]
        success = publish_command(
            device.device_code,
            {"request_id": child_request_id, **parameters},
        )
        # An ACK can arrive while publish waits. Never overwrite a later state.
        current = session.exec(
            select(Command).where(Command.id == parent.id).with_for_update()
            .execution_options(populate_existing=True)
        ).one()
        next_status = "SENT" if success else "FAILED"
        # A matching ACK can reach the consumer before publish() returns.
        # A local publish failure cannot overturn an ACK already received.
        if not success and current.dispatches[key]["status"] not in {"PENDING", "SENT"}:
            next_status = current.dispatches[key]["status"]
        current.dispatches = update_dispatch(
            current.dispatches, key, next_status,
            None if success or next_status != "FAILED" else "MQTT publish failed",
        )
        aggregate(current)
        session.add(current)
        session.commit()
    session.refresh(parent)
    return _public(session, parent, device)


@router.post("/devices/{device_id}/commands", status_code=201)
def send_test_alert(
    device_id: int,
    data: TestAlertRequest,
    current_user: User = Depends(require_operator),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.device_type != "ALERT_NODE":
        raise HTTPException(status_code=409, detail="Device is not an alert node")
    if device.lifecycle_state != "ACTIVE":
        raise HTTPException(status_code=409, detail="Device is not active")
    if device.status != "ONLINE" or not _fresh(device.last_seen):
        raise HTTPException(status_code=409, detail="Device is offline or heartbeat is stale")

    # Firmware 0.2.10 receives one command per output. One web request has
    # three distinct child IDs so ACKs can be matched without changing firmware.
    led_duration = max(1000, data.buzzer_ms, data.vibration_ms)
    actions = {
        "led": {
            "command": "LED_ON", "duration": led_duration,
            "intensity": "CONSTANT" if data.led_mode == "ON" else "MEDIUM",
        },
        "buzzer": {
            "command": "BUZZER_ON", "duration": data.buzzer_ms,
            "intensity": "MEDIUM",
        },
        "motor": {
            "command": "MOTOR_ON", "duration": data.vibration_ms,
            "intensity": "MEDIUM",
        },
    }
    parent = _save_parent(session, device, current_user, data.action, actions)
    log_action(
        session=session, user_id=current_user.id, action="TEST_ALERT",
        entity_type="Command", entity_id=parent.request_id,
        details={"device_code": device.device_code},
    )
    session.commit()
    return _publish_actions(session, parent, device, actions)


@router.get("/commands")
def list_commands(
    device_id: int | None = None,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    if device_id is not None:
        assigned_device(session, current_user.id, device_id)
    query = (
        select(Command)
        .join(UserDevice, UserDevice.device_id == Command.device_id)
        .where(UserDevice.user_id == current_user.id, UserDevice.unassigned_at.is_(None))
        .distinct()
    )
    if device_id is not None:
        query = query.where(Command.device_id == device_id)
    commands = session.exec(query.order_by(Command.created_at.desc()).limit(100)).all()
    return [_public(session, command) for command in commands]


@router.get("/commands/{request_id}")
def get_command(
    request_id: str,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    command = session.exec(
        select(Command).where(Command.request_id == request_id)
    ).first()
    if command is None and request_id.startswith("cmd-") and request_id[4:].isdigit():
        command = session.get(Command, int(request_id[4:]))
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    assigned_device(session, current_user.id, command.device_id)
    return _public(session, command)


@router.post("/commands/", status_code=201)
def send_command_legacy(
    data: LegacyCommandRequest,
    current_user: User = Depends(require_operator),
    session: Session = Depends(get_session),
):
    device = session.exec(
        select(Device).where(Device.device_code == data.device_code)
    ).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    assigned_device(session, current_user.id, device.id)
    if device.lifecycle_state != "ACTIVE" or device.status != "ONLINE":
        raise HTTPException(status_code=409, detail="Device is not active and online")
    command_name = {"VIBRATION_ON": "MOTOR_ON", "VIBRATION_OFF": "MOTOR_OFF"}.get(
        data.command, data.command
    )
    if command_name not in {"LED_ON", "LED_OFF", "BUZZER_ON", "BUZZER_OFF", "MOTOR_ON", "MOTOR_OFF"}:
        raise HTTPException(status_code=422, detail="Unsupported firmware command")
    actions = {"output": {
        "command": command_name,
        "duration": data.duration,
        "intensity": data.intensity,
    }}
    parent = _save_parent(session, device, current_user, data.command, actions)
    return _publish_actions(session, parent, device, actions)
