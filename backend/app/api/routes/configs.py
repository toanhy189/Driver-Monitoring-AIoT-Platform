from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import require_operator, require_viewer
from app.core.db import get_session
from app.models.config import Config
from app.models.device import Device
from app.models.user import User
from app.schemas.config import validate_timings
from app.services.access import assigned_device
from app.services.audit_service import log_action


router = APIRouter(tags=["configs"])


class ConfigUpdateRequest(BaseModel):
    timings: dict


def _config_for(session: Session, device_id: int) -> Config | None:
    return session.exec(select(Config).where(Config.device_id == device_id)).first()


def _snapshot(config: Config | None) -> dict:
    desired = config.desired_config if config else None
    applied = config.applied_config if config else None
    desired = desired if isinstance(desired, dict) and "timings" in desired else None
    applied = applied if isinstance(applied, dict) and "timings" in applied else None
    return {
        "config_id": desired.get("config_id") if desired else None,
        "applied_config_id": applied.get("config_id") if applied else None,
        "desired": desired,
        "applied": applied,
    }


@router.get("/devices/{device_id}/config")
def get_device_config(
    device_id: int,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.device_type != "ALERT_NODE":
        raise HTTPException(status_code=409, detail="Device is not an alert node")
    return _snapshot(_config_for(session, device_id))


@router.put("/devices/{device_id}/config")
def update_device_config(
    device_id: int,
    data: ConfigUpdateRequest,
    current_user: User = Depends(require_operator),
    session: Session = Depends(get_session),
):
    device = assigned_device(session, current_user.id, device_id)
    if device.device_type != "ALERT_NODE":
        raise HTTPException(status_code=409, detail="Device is not an alert node")
    if device.lifecycle_state == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Device decommissioned")
    timings = validate_timings(data.timings)
    config = _config_for(session, device_id)
    if config is None:
        config = Config(device_id=device_id)
    config_id = f"cfg-{uuid4().hex}"
    config.desired_config = {"config_id": config_id, "timings": timings}
    config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(config)
    session.commit()
    log_action(
        session=session, user_id=current_user.id, action="UPDATE_CONFIG",
        entity_type="Config", entity_id=str(config.id),
        details={"device_code": device.device_code, "config_id": config_id},
    )
    session.commit()
    # Current firmware has no config subscription or applied ACK. Keep it pending.
    return {"config_id": config_id, "status": "PENDING_APPLICATION"}


@router.get("/configs/{device_code}")
def get_config_legacy(
    device_code: str,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    device = session.exec(select(Device).where(Device.device_code == device_code)).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    assigned_device(session, current_user.id, device.id)
    config = _config_for(session, device.id)
    return {
        "device_code": device_code,
        "desired_config": config.desired_config if config else None,
        "applied_config": config.applied_config if config else None,
        "updated_at": config.updated_at if config else None,
    }


@router.post("/configs/{device_code}")
def update_config_legacy(
    device_code: str,
    data: dict,
    current_user: User = Depends(require_operator),
    session: Session = Depends(get_session),
):
    device = session.exec(select(Device).where(Device.device_code == device_code)).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    assigned_device(session, current_user.id, device.id)
    desired = data.get("desired_config")
    timings = desired.get("timings") if isinstance(desired, dict) else None
    if timings is None:
        raise HTTPException(status_code=422, detail="desired_config.timings is required")
    return update_device_config(
        device.id, ConfigUpdateRequest(timings=timings), current_user, session
    )
