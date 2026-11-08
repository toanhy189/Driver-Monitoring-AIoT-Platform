from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import require_operator, require_viewer
from app.core.db import get_session
from app.models.alert import Alert
from app.models.device import Device
from app.models.user import User
from app.models.user_device import UserDevice
from app.models.command import Command
from app.services.access import assigned_device
from app.services.audit_service import log_action
from app.services.time_utils import as_utc
from app.services.event_links import video_for_alert, video_summary
from datetime import datetime, timezone

VIDEO_PENDING_WINDOW_SECONDS = 1800   # tùy chỉnh; video chỉ lên khi segment kết thúc

router = APIRouter(tags=["alerts"])


def _public(session: Session, alert: Alert, user_id: int | None = None) -> dict:
    device = session.get(Device, alert.device_id)
    severity = alert.severity
    command_query = select(Command).where(Command.alert_id == alert.id)
    if user_id is not None:
        command_query = command_query.join(UserDevice, UserDevice.device_id == Command.device_id).where(
            UserDevice.user_id == user_id, UserDevice.unassigned_at.is_(None))
    command = session.exec(command_query.order_by(Command.id).limit(1)).first()

    video = video_for_alert(session, alert)
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - alert.created_at).total_seconds() if alert.created_at else 0

    return {
        "alert_id": alert.id,
        "device_id": alert.device_id,
        "device_code": device.device_code if device else None,
        "alert_type": alert.alert_type,
        "severity": int(severity) if severity is not None and str(severity).isdigit() else None,
        "description": alert.description,
        "created_at": as_utc(alert.created_at),
        "status": alert.status,
        "request_id": command.request_id if command else None,
        "event_id": alert.source_event_id, # giữ nguyên cho FE cũ
        "video": video_summary(video) if video else None,
        "video_status": "READY" if video else ("PENDING" if age < VIDEO_PENDING_WINDOW_SECONDS else "UNAVAILABLE"), # không để trạng thái "PENDING" quá lâu
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
        assigned_device(session, current_user, device_id)
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
    return [_public(session, alert, current_user.id) for alert in alerts]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user: User = Depends(require_operator),
    session: Session = Depends(get_session),
):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    assigned_device(session, current_user, alert.device_id)
    if alert.status == "ACKNOWLEDGED":
        return _public(session, alert, current_user.id)
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
    return _public(session, alert, current_user.id)

@router.get("/alerts/{alert_id}/video")
def alert_video(alert_id: int, current_user: User = Depends(require_viewer),
                session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    assigned_device(session, current_user, alert.device_id)
    video = video_for_alert(session, alert)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not available yet")
    return video_summary(video)