from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import app.core.security as acs
from app.core.db import get_session

from app.models.device import Device
from app.models.user_device import UserDevice

from app.schemas.device import DeviceResponse
from app.schemas.telemetry import TelemetryResponse

router = APIRouter(
    prefix="",
    tags=["devices"],
)

@router.post("/devices", response_model= list[DeviceResponse])
def get_all_device(session: Session = Depends(get_session)):
    user_id = acs.get_current_user_id()
    devices = session.exec(
        select(Device)
        .join(UserDevice, UserDevice.device_id == Device.id)
        .where(UserDevice.user_id == user_id)
    ).all()
    return devices

@router.post("/ws/telemetry", response_model= TelemetryResponse)
def get_users(session: Session = Depends(get_session)):
    return session.exec().all()
