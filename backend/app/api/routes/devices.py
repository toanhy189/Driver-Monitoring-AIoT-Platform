from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlmodel import Session, select

from app.api.deps import require_admin, require_viewer
from app.core.db import get_session
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.user_device import UserDevice
from app.schemas.device import DeviceRegisterRequest, DeviceResponse, DeviceStatusRequest, ProvisionResponse, HardwareVersionUpdate
from app.schemas.telemetry import TelemetryHistoryItem, TelemetryHistoryResponse, TelemetryResponse
from app.services.access import assigned_device, assigned_devices, is_admin, require_vision_node
from app.services.audit_service import log_action
from app.services.mqtt_provision_service import provision_device
from app.services.mqtt_revoke_service import revoke_device
from app.services.time_utils import as_utc


router = APIRouter(tags=["devices"])


def require_device_manager(
    device_id: int,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
) -> User:
    if is_admin(current_user):
        return current_user
    if current_user.role not in {"Employee", "OPERATOR"}:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    try:
        assigned_device(session, current_user, device_id)
    except HTTPException as error:
        if error.status_code != 404:
            raise
        raise HTTPException(status_code=403, detail="Not enough permissions") from error
    return current_user


def _response(device: Device) -> DeviceResponse:
    return DeviceResponse.from_device(device)


@router.patch("/devices/{device_id}/hardware", response_model=DeviceResponse)
def update_hardware_version(device_id: int, data: HardwareVersionUpdate,
                            current_user: User = Depends(require_device_manager),
                            session: Session = Depends(get_session)):
    device = assigned_device(session, current_user, device_id)
    value = data.hardware_version.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Hardware version cannot be blank")
    device.hardware_version = value
    session.add(device)
    log_action(session, current_user.id, "UPDATE_HARDWARE_VERSION", "Device", str(device.id))
    session.commit()
    session.refresh(device)
    return _response(device)


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
    return [_response(device) for device in assigned_devices(session, current_user)]


@router.get("/devices/{device_id}", response_model=DeviceResponse)
def get_device_detail(
    device_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_viewer),
):
    return _response(assigned_device(session, current_user, device_id))


@router.get("/{device_id}/telemetry", response_model=TelemetryResponse)
def get_current_telemetry(
    device_id: int,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user, device_id)
    require_vision_node(device)
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
        confidence=telemetry.confidence,
        face_detected=telemetry.face_detected,
        head_pose=telemetry.head_pose,
        model_version=telemetry.model_version,
    )


@router.get("/{device_id}/telemetry/history", response_model=TelemetryHistoryResponse)
def get_telemetry_history(
    device_id: int,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user, device_id)
    require_vision_node(device)
    for value in (from_time, to_time):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(status_code=422, detail="from_time/to_time must include a UTC offset")
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(status_code=422, detail="Expected from_time < to_time")
    query = select(Telemetry).where(Telemetry.device_id == device_id)
    if from_time:
        query = query.where(Telemetry.recorded_at >= from_time.astimezone(timezone.utc).replace(tzinfo=None))
    if to_time:
        query = query.where(Telemetry.recorded_at < to_time.astimezone(timezone.utc).replace(tzinfo=None))

    # Query descending to get the most recent samples up to limit
    items_desc = session.exec(query.order_by(Telemetry.recorded_at.desc(), Telemetry.id.desc()).limit(limit)).all()
    # Reverse to ascending chronological order for timeline / charts
    items_asc = list(reversed(items_desc))
    total_samples = len(items_asc)
    latest_item = items_desc[0] if items_desc else None

    return TelemetryHistoryResponse(
        device_id=device.id,
        device_code=device.device_code,
        total_samples=total_samples,
        model_version=latest_item.model_version if latest_item else None,
        last_updated=as_utc(latest_item.recorded_at) if latest_item else None,
        items=[
            TelemetryHistoryItem(
                id=t.id,
                recorded_at=t.recorded_at,
                ear=t.ear,
                perclos=t.perclos,
                driver_state=t.driver_state,
                confidence=t.confidence,
                face_detected=t.face_detected,
                model_version=t.model_version,
            )
            for t in items_asc
        ],
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
        hardware_version=data.hardware_version,
        device_type=_kind(data.device_code, data.model),
        ip_address=data.ip_address,
        mac_address=data.mac_address,
        status="OFFLINE",
        lifecycle_state="REGISTERED",
    )
    session.add(device)
    session.flush()
    session.add(UserDevice(user_id=current_user.id, device_id=device.id))
    # Dang ky truoc day chi tao device va assignment; audit cung giao dich.
    log_action(
        session, current_user.id, "REGISTER_DEVICE", "Device", str(device.id),
        {"device_code": device.device_code, "to_state": device.lifecycle_state},
    )
    session.commit()
    session.refresh(device)
    return {"message": "Device registered", "device": _response(device)}


@router.post("/devices/{device_id}/provision", response_model=ProvisionResponse)
def provision_mqtt_credentials(
    device_id: int,
    response: Response,
    current_user: User = Depends(require_device_manager),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user, device_id)
    if device.lifecycle_state != "REGISTERED":
        raise HTTPException(status_code=409, detail="Only registered devices can be provisioned")
    try:
        credentials = provision_device(device.device_code, device_type=device.device_type)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MQTT provisioning unavailable: {error}")
    device.mqtt_username = credentials["username"]
    device.mqtt_password = None
    device.lifecycle_state = "PROVISIONED"
    session.add(device)
    # Provision truoc day khong audit; chi ghi username metadata, khong ghi password.
    log_action(
        session, current_user.id, "PROVISION_DEVICE_CREDENTIALS", "Device", str(device.id),
        {"device_code": device.device_code, "from_state": "REGISTERED", "to_state": "PROVISIONED"},
    )
    session.commit()
    session.refresh(device)
    response.headers["Cache-Control"] = "no-store"
    return ProvisionResponse.model_validate({
        **_response(device).model_dump(),
        "mqtt_username": credentials["username"],
        "mqtt_password": credentials["password"],
    })


@router.post("/devices/{device_id}/activate", response_model=DeviceResponse)
def activate_device(
    device_id: int,
    current_user: User = Depends(require_device_manager),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user, device_id)
    if device.lifecycle_state not in {"PROVISIONED", "MAINTENANCE"}:
        raise HTTPException(status_code=409, detail="Device must be provisioned or in maintenance")
    previous_state = device.lifecycle_state
    device.lifecycle_state = "ACTIVE"
    session.add(device)
    # Audit ghi lai actor va buoc chuyen state ma khong can luu thong tin bi mat.
    log_action(
        session, current_user.id, "ACTIVATE_DEVICE", "Device", str(device.id),
        {"device_code": device.device_code, "from_state": previous_state, "to_state": "ACTIVE"},
    )
    session.commit()
    session.refresh(device)
    return _response(device)


@router.post("/devices/{device_id}/maintenance", response_model=DeviceResponse)
def maintain_device(
    device_id: int,
    current_user: User = Depends(require_device_manager),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user, device_id)
    if device.lifecycle_state != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only active devices can enter maintenance")
    previous_state = device.lifecycle_state
    device.lifecycle_state = "MAINTENANCE"
    session.add(device)
    # Ghi nhan thao tac dua thiet bi vao bao tri de doi chieu vong doi thiet bi.
    log_action(
        session, current_user.id, "DEVICE_MAINTENANCE", "Device", str(device.id),
        {"device_code": device.device_code, "from_state": previous_state, "to_state": "MAINTENANCE"},
    )
    session.commit()
    session.refresh(device)
    return _response(device)


@router.post("/devices/{device_id}/decommission", response_model=DeviceResponse)
def decommission_device(
    device_id: int,
    current_user: User = Depends(require_device_manager),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user, device_id)
    if device.lifecycle_state == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Device already decommissioned")
    if device.mqtt_username:
        try:
            revoke_device(device.device_code)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        except Exception as error:
            raise HTTPException(status_code=503, detail=f"MQTT revoke unavailable: {error}")
    previous_state = device.lifecycle_state
    device.lifecycle_state = "DECOMMISSIONED"
    device.status = "OFFLINE"
    device.mqtt_username = None
    device.mqtt_password = None
    session.add(device)
    # Decommission truoc day chi doi state; audit ghi ket qua revoke, khong ghi credential.
    log_action(
        session, current_user.id, "DECOMMISSION_DEVICE", "Device", str(device.id),
        {"device_code": device.device_code, "from_state": previous_state, "to_state": "DECOMMISSIONED"},
    )
    session.commit()
    session.refresh(device)
    return _response(device)


@router.patch("/devices/{device_id}/status", response_model=DeviceResponse)
def update_device_status(
    device_id: int,
    data: DeviceStatusRequest,
    current_user: User = Depends(require_device_manager),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user, device_id)
    if device.lifecycle_state == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Device decommissioned")
    if data.status not in {"ONLINE", "OFFLINE"}:
        raise HTTPException(status_code=422, detail="Invalid connection status")
    device.status = data.status
    session.add(device)
    # Audit cap nhat trang thai ket noi de truy vet thao tac quan tri.
    log_action(
        session, current_user.id, "UPDATE_DEVICE_STATUS", "Device", str(device.id),
        {"device_code": device.device_code, "status": data.status},
    )
    session.commit()
    session.refresh(device)
    return _response(device)
