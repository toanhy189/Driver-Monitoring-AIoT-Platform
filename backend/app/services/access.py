from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.device import Device
from app.models.user import User
from app.models.user_device import UserDevice


def is_admin(user: User) -> bool:
    return user.role in {"Admin", "ADMIN"}


def assigned_device(session: Session, current_user: User, device_id: int) -> Device:
    query = select(Device).where(Device.id == device_id)
    if not is_admin(current_user):
        query = (
            query.join(UserDevice, UserDevice.device_id == Device.id)
            .where(
                UserDevice.user_id == current_user.id,
                UserDevice.unassigned_at.is_(None),
            )
        )
    device = session.exec(query).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


def require_vision_node(device: Device) -> None:
    if device.device_type != "VISION_NODE":
        raise HTTPException(status_code=409, detail="Telemetry and metrics are only available for vision nodes")


def assigned_devices(session: Session, current_user: User) -> list[Device]:
    query = select(Device)
    if not is_admin(current_user):
        query = (
            query.join(UserDevice, UserDevice.device_id == Device.id)
            .where(
                UserDevice.user_id == current_user.id,
                UserDevice.unassigned_at.is_(None),
            )
            .distinct()
        )
    return session.exec(query).all()
