from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import require_operator, require_viewer
from app.core.db import get_session
from app.models.alert import Alert
from app.models.device import Device
from app.models.user import User
from app.models.user_device import UserDevice
from app.services.access import assigned_device
from app.services.audit_service import log_action
from app.services.time_utils import as_utc


router = APIRouter(tags=["alerts"])


def _public(session: Session, alert: Alert) -> dict:
    device = session.get(Device, alert.device_id)
    severity = alert.severity
    return {
        "alert_id": alert.id,
        "device_id": alert.device_id,
        "device_code": device.device_code if device else None,
        "alert_type": alert.alert_type,
        "severity": int(severity) if severity is not None and str(severity).isdigit() else None,
        "description": alert.description,
        "created_at": as_utc(alert.created_at),
        "status": alert.status,
        "request_id": None,
    }


@router.get("/alerts")
def list_alerts(
    device_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_viewer),
    session: Session = Depends(get_session),
):
    if device_id is not None:
        assigned_device(session, current_user.id, device_id)
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    query = (
        select(Alert)
        .join(UserDevice, UserDevice.device_id == Alert.device_id)
        .where(UserDevice.user_id == current_user.id, UserDevice.unassigned_at.is_(None))
        .distinct()
    )
    if device_id is not None:
        query = query.where(Alert.device_id == device_id)
    if status is not None:
        query = query.where(Alert.status == status)
    alerts = session.exec(
        query.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [_public(session, alert) for alert in alerts]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user: User = Depends(require_operator),
    session: Session = Depends(get_session),
):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    assigned_device(session, current_user.id, alert.device_id)
    if alert.status == "ACKNOWLEDGED":
        return _public(session, alert)
    if alert.status != "NEW":
        raise HTTPException(status_code=409, detail="Alert cannot be acknowledged")
    alert.status = "ACKNOWLEDGED"
    session.add(alert)
    session.commit()
    log_action(
        session=session, user_id=current_user.id,
        action="ACKNOWLEDGE_ALERT", entity_type="Alert",
        entity_id=str(alert.id), details={"alert_type": alert.alert_type},
    )
    session.commit()
    return _public(session, alert)
