from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import app.core.security as acs
from app.core.db import get_session

from app.models.device import Device
from app.models.user_device import UserDevice
from app.models.telemetry import Telemetry

from app.schemas.device import DeviceResponse
from app.schemas.telemetry import TelemetryResponse

router = APIRouter(
    prefix="",
    tags=["devices"],
)

@router.get("/devices", response_model= list[DeviceResponse])
def get_all_device(
    session: Session = Depends(get_session),
    user_id: int = Depends(acs.get_current_user_id)
):
    devices = session.exec(
        select(Device)
        .join(UserDevice, UserDevice.device_id == Device.id)
        .where(UserDevice.user_id == user_id)
    ).all()

    print(devices)
    return devices

## API đang sử dụng database ID. 
'''Nếu muốn frontend cũng hoàn toàn dùng device_code, tốt hơn là sau này thiết kế:
GET /api/devices/{device_code}/telemetry

Ví dụ:
GET /api/devices/DM-000001/telemetry
'''
@router.get("/{device_id}/telemetry", response_model= TelemetryResponse)
def get_current_telemetry(
    device_id: int,
    user_id: int = Depends(acs.get_current_user_id),
    session: Session = Depends(get_session)
):
    telemetry = session.exec(
        select(Telemetry)
        .join(
            UserDevice,
            UserDevice.device_id == Telemetry.device_id
        )
        .where(
            Telemetry.device_id == device_id,
            UserDevice.user_id == user_id
        )
        .order_by(Telemetry.recorded_at.desc())
    ).first()

    print("device_id =", device_id)
    print("user_id =", user_id)
    print("telemetry =", telemetry)

    return telemetry
