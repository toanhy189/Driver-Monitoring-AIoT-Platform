from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

import app.core.security as acs
from app.api.deps import require_admin
from app.core.db import get_session
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.device import DeviceRegisterRequest, DeviceResponse, DeviceStatusRequest
from app.schemas.telemetry import TelemetryResponse
from app.services.mqtt_provision_service import provision_device
from app.services.mqtt_revoke_service import revoke_device


router = APIRouter(tags=["devices"])


@router.get("/devices", response_model=list[DeviceResponse])
def get_all_device(
    session: Session = Depends(get_session),
    user_id: int = Depends(acs.get_current_user_id),
):
    return session.exec(
        select(Device)
        .join(UserDevice, UserDevice.device_id == Device.id)
        .where(UserDevice.user_id == user_id, UserDevice.unassigned_at.is_(None))
    ).all()


@router.get("/{device_id}/telemetry", response_model=TelemetryResponse)
def get_current_telemetry(
    device_id: int,
    user_id: int = Depends(acs.get_current_user_id),
    session: Session = Depends(get_session),
):
    telemetry = session.exec(
        select(Telemetry)
        .join(UserDevice, UserDevice.device_id == Telemetry.device_id)
        .where(
            Telemetry.device_id == device_id,
            UserDevice.user_id == user_id,
            UserDevice.unassigned_at.is_(None),
        )
        .order_by(Telemetry.recorded_at.desc())
    ).first()
    if telemetry is None:
        raise HTTPException(status_code=404, detail="Telemetry not found")

    device = session.get(Device, device_id)
    return TelemetryResponse(
        device_id=device_id,
        device_code=device.device_code,
        model=device.model,
        name=device.name,
        recorded_at=telemetry.recorded_at,
        ear=telemetry.ear,
        perclos=telemetry.perclos,
        driver_state=telemetry.driver_state,
        angle_x=telemetry.angle_x,
        angle_y=telemetry.angle_y,
        angle_z=telemetry.angle_z,
        confidence=telemetry.confidence,
    )


@router.post("/devices", status_code=201)
@router.post("/devices/register", status_code=201)
def register_device(
    data: DeviceRegisterRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if session.exec(select(Device).where(Device.device_code == data.device_code)).first():
        raise HTTPException(status_code=409, detail="Device code already exists")

    device = Device(
        device_code=data.device_code,
        model=data.model,
        name=data.name,
        ip_address=data.ip_address,
        mac_address=data.mac_address,
        status="OFFLINE",
    )
    session.add(device)
    session.flush()
    session.add(UserDevice(user_id=current_user.id, device_id=device.id))
    session.commit()
    session.refresh(device)
    return {
        "message": "Device registered successfully",
        "device": DeviceResponse.model_validate(device, from_attributes=True),
    }


@router.patch("/devices/{device_id}/status")
def update_device_status(
    device_id: int,
    data: DeviceStatusRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if data.status not in {"OFFLINE", "ONLINE", "DECOMMISSIONED"}:
        raise HTTPException(status_code=422, detail="Invalid device status")
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.status == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Decommissioned device cannot change status")

    if data.status == "DECOMMISSIONED":
        try:
            revoke_device(device.device_code)
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"Failed to revoke MQTT credential: {error}")

    device.status = data.status
    session.add(device)
    session.commit()
    session.refresh(device)
    return {
        "message": "Device status updated successfully",
        "device": DeviceResponse.model_validate(device, from_attributes=True),
    }


@router.post("/devices/{device_id}/provision")
def provision_mqtt_credentials(
    device_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.status == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Decommissioned device cannot be provisioned")

    try:
        credentials = provision_device(device.device_code)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    device.mqtt_username = credentials["username"]
    device.mqtt_password = credentials["password"]
    session.add(device)
    session.commit()
    return {
        "message": "MQTT credentials provisioned successfully",
        "device_code": device.device_code,
        "mqtt_username": credentials["username"],
        "mqtt_password": credentials["password"],
    }
