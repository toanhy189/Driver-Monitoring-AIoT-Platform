from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import CurrentUser, require_operator
from app.core.db import get_session
from app.models.device import Device
from app.models.user import User
from app.schemas.device import (
    DeviceRegisterRequest,
    DeviceStatusRequest,
)
from app.services.mqtt_provision_service import provision_device
from app.services.mqtt_revoke_service import revoke_device

router = APIRouter(
    prefix="/devices",
    tags=["devices"],
)


@router.post("/register")
def register_device(
    data: DeviceRegisterRequest,
    current_user: Annotated[
        User,
        Depends(require_operator),
    ],
    session: Session = Depends(get_session),
):
    existing_device = session.exec(
        select(Device).where(
            Device.device_code == data.device_code
        )
    ).first()

    if existing_device:
        raise HTTPException(
            status_code=400,
            detail="Device code already exists",
        )

    device = Device(
        device_code=data.device_code,
        model=data.model,
        name=data.name,
        ip_address=data.ip_address,
        mac_address=data.mac_address,
        status="OFFLINE",
    )

    session.add(device)
    session.commit()
    session.refresh(device)

    return {
        "message": "Device registered successfully",
        "device": device,
    }


@router.get("/")
def get_devices(
    current_user: CurrentUser,
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Device)
    ).all()


@router.patch("/{device_id}/status")
def update_device_status(
    device_id: int,
    data: DeviceStatusRequest,
    current_user: Annotated[
        User,
        Depends(require_operator),
    ],
    session: Session = Depends(get_session),
):
    allowed_statuses = {
        "OFFLINE",
        "ONLINE",
        "DECOMMISSIONED",
    }

    if data.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid device status",
        )

    device = session.get(Device, device_id)

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )

    if device.status == "DECOMMISSIONED":
        raise HTTPException(
            status_code=400,
            detail="Decommissioned device cannot change status",
        )

    # Nếu chuyển sang DECOMMISSIONED
    # thì revoke MQTT credential trước
    if data.status == "DECOMMISSIONED":
        try:
            revoke_device(device.device_code)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to revoke MQTT credential: {e}",
            )

    device.status = data.status

    session.add(device)
    session.commit()
    session.refresh(device)

    return {
        "message": "Device status updated successfully",
        "device": device,
    }
@router.post("/{device_id}/provision")
def provision_mqtt_credentials(
    device_id: int,
    current_user: Annotated[
        User,
        Depends(require_operator),
    ],
    session: Session = Depends(get_session),
):
    device = session.get(Device, device_id)

    if device is None:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )

    if device.status == "DECOMMISSIONED":
        raise HTTPException(
            status_code=400,
            detail="Decommissioned device cannot be provisioned",
        )

    try:
        credentials = provision_device(
            device.device_code
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    # Lưu MQTT credential vào database
    device.mqtt_username = credentials["username"]
    device.mqtt_password = credentials["password"]

    session.add(device)
    session.commit()
    session.refresh(device)

    return {
        "message": "MQTT credentials provisioned successfully",
        "device_code": device.device_code,
        "mqtt_username": credentials["username"],
        "mqtt_password": credentials["password"],
    }