from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, update

from app.api.deps import require_operator
from app.core.db import get_session
from app.models.command import Command
from app.models.command_type import CommandType
from app.models.device import Device
from app.models.user import User
from app.services.command_service import publish_command
from app.services.audit_service import log_action


router = APIRouter(
    prefix="/commands",
    tags=["commands"],
)


class CommandRequest(BaseModel):
    device_code: str
    command: str


@router.post("/")
def send_command(
    data: CommandRequest,
    current_user: Annotated[
        User,
        Depends(require_operator),
    ],
    session: Session = Depends(get_session),
):
    # 1. Kiểm tra device có tồn tại không
    device = session.exec(
        select(Device).where(
            Device.device_code == data.device_code
        )
    ).first()

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )

    # 2. Không cho gửi command tới device đã decommission
    if device.status == "DECOMMISSIONED":
        raise HTTPException(
            status_code=400,
            detail="Cannot send command to decommissioned device",
        )

    # 3. Kiểm tra command type
    command_type = session.exec(
        select(CommandType).where(
            CommandType.code == data.command
        )
    ).first()

    if command_type is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid command type",
        )

    # 4. Kiểm tra MQTT credential
    if not device.mqtt_username or not device.mqtt_password:
        raise HTTPException(
            status_code=400,
            detail="Device MQTT credentials not provisioned",
        )

    # 5. Lưu command với trạng thái PENDING
    command = Command(
        device_id=device.id,
        command_type_id=command_type.id,
        status="PENDING",
    )

    session.add(command)
    session.commit()
    session.refresh(command)
    
    log_action(
        session=session,
        user_id=current_user.id,
        action="SEND_COMMAND",
        entity_type="Command",
        entity_id=str(command.id),
        details={"device_code": data.device_code, "command": data.command}
    )
    session.commit()

    # 6. Publish MQTT
    success = publish_command(
        command_id=command.id,
        device_code=device.device_code,
        command=data.command,
        mqtt_username=device.mqtt_username,
        mqtt_password=device.mqtt_password,
    )

    if not success:
        return {
            "message": "Command saved but MQTT publish failed",
            "command_id": command.id,
            "device_code": device.device_code,
            "command": data.command,
            "status": "PENDING",
        }

    # Cập nhật trạng thái thành SENT nếu đang là PENDING
    # (Để tránh ghi đè lên ACKED nếu thiết bị gửi ACK quá nhanh)
    session.exec(
        update(Command)
        .where(Command.id == command.id)
        .where(Command.status == "PENDING")
        .values(status="SENT")
    )
    session.commit()
    session.refresh(command)

    return {
        "message": "Command created and published successfully",
        "command_id": command.id,
        "device_code": device.device_code,
        "command": data.command,
        "status": command.status,
    }