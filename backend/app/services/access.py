from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.device import Device
from app.models.user_device import UserDevice


def assigned_device(session: Session, user_id: int, device_id: int) -> Device:
    device = session.exec(
        select(Device)
        .join(UserDevice, UserDevice.device_id == Device.id)
        .where(
            Device.id == device_id,
            UserDevice.user_id == user_id,
            UserDevice.unassigned_at.is_(None),
        )
    ).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


def assigned_devices(session: Session, user_id: int) -> list[Device]:
    return session.exec(
        select(Device)
        .join(UserDevice, UserDevice.device_id == Device.id)
        .where(UserDevice.user_id == user_id, UserDevice.unassigned_at.is_(None))
        .distinct()
    ).all()
