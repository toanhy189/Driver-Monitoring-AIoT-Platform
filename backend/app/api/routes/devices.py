from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import require_admin, require_viewer
from app.core.db import get_session
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.device import DeviceRegisterRequest, DeviceResponse, DeviceStatusRequest
from app.schemas.telemetry import TelemetryResponse
from app.services.access import assigned_device, assigned_devices
from app.services.mqtt_provision_service import provision_device
from app.services.mqtt_revoke_service import revoke_device


router = APIRouter(tags=["devices"])


def _response(device: Device) -> DeviceResponse:
    return DeviceResponse.from_device(device)


def _kind(code: str, model: str) -> str | None:
    value = f"{code} {model}".lower()
    if code.lower().startswith("alert-") or "alert" in value or "cảnh báo" in value:
        return "ALERT_NODE"
    if code.lower().startswith("vision-") or "cam" in value:
        return "VISION_NODE"
    return None


@router.get("/devices", response_model=list[DeviceResponse])
def get_all_device(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_viewer),
):
    return [_response(device) for device in assigned_devices(session, current_user.id)]


@router.get("/devices/{device_id}", response_model=DeviceResponse)
def get_device_detail(
    device_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_viewer),
):
    return _response(assigned_device(session, current_user.id, device_id))


@router.get("/{device_id}/telemetry", response_model=TelemetryResponse)
def get_current_telemetry(
    device_id: int,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    telemetry = session.exec(
        select(Telemetry)
        .where(Telemetry.device_id == device_id)
        .order_by(Telemetry.recorded_at.desc())
    ).first()
    if telemetry is None:
        raise HTTPException(status_code=404, detail="Telemetry not found")
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
        face_detected=telemetry.face_detected,
        head_pose=telemetry.head_pose,
        model_version=telemetry.model_version,
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
        device_type=_kind(data.device_code, data.model),
        ip_address=data.ip_address,
        mac_address=data.mac_address,
        status="OFFLINE",
        lifecycle_state="REGISTERED",
    )
    session.add(device)
    session.flush()
    session.add(UserDevice(user_id=current_user.id, device_id=device.id))
    session.commit()
    session.refresh(device)
    return {"message": "Device registered", "device": _response(device)}


@router.post("/devices/{device_id}/provision", response_model=DeviceResponse)
def provision_mqtt_credentials(
    device_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.lifecycle_state != "REGISTERED":
        raise HTTPException(status_code=409, detail="Only registered devices can be provisioned")
    try:
        credentials = provision_device(device.device_code)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MQTT provisioning unavailable: {error}")
    device.mqtt_username = credentials["username"]
    device.mqtt_password = credentials["password"]
    device.lifecycle_state = "PROVISIONED"
    session.add(device)
    session.commit()
    session.refresh(device)
    return _response(device)


@router.post("/devices/{device_id}/activate", response_model=DeviceResponse)
def activate_device(
    device_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.lifecycle_state not in {"PROVISIONED", "MAINTENANCE"}:
        raise HTTPException(status_code=409, detail="Device must be provisioned or in maintenance")
    device.lifecycle_state = "ACTIVE"
    session.add(device)
    session.commit()
    session.refresh(device)
    return _response(device)


@router.post("/devices/{device_id}/maintenance", response_model=DeviceResponse)
def maintain_device(
    device_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.lifecycle_state != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only active devices can enter maintenance")
    device.lifecycle_state = "MAINTENANCE"
    session.add(device)
    session.commit()
    session.refresh(device)
    return _response(device)


@router.post("/devices/{device_id}/decommission", response_model=DeviceResponse)
def decommission_device(
    device_id: int,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.lifecycle_state == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Device already decommissioned")
    if device.mqtt_username:
        try:
            revoke_device(device.device_code)
        except Exception as error:
            raise HTTPException(status_code=503, detail=f"MQTT revoke unavailable: {error}")
    device.lifecycle_state = "DECOMMISSIONED"
    device.status = "OFFLINE"
    device.mqtt_username = None
    device.mqtt_password = None
    session.add(device)
    session.commit()
    session.refresh(device)
    return _response(device)


@router.patch("/devices/{device_id}/status", response_model=DeviceResponse)
def update_device_status(
    device_id: int,
    data: DeviceStatusRequest,
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.lifecycle_state == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Device decommissioned")
    if data.status not in {"ONLINE", "OFFLINE"}:
        raise HTTPException(status_code=422, detail="Invalid connection status")
    device.status = data.status
    session.add(device)
    session.commit()
    session.refresh(device)
    return _response(device)
