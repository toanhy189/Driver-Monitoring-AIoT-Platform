from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import require_operator, require_viewer
from app.core.db import get_session
from app.models.alert import Alert
from app.models.user import User
from app.services.audit_service import log_action

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
)

@router.get("/")
def list_alerts(
    current_user: Annotated[User, Depends(require_viewer)],
    session: Session = Depends(get_session),
    device_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0
):
    query = select(Alert)
    
    if device_id is not None:
        query = query.where(Alert.device_id == device_id)
        
    if status is not None:
        query = query.where(Alert.status == status)
        
    query = query.offset(offset).limit(limit)
    alerts = session.exec(query).all()
    
    return alerts


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user: Annotated[User, Depends(require_operator)],
    session: Session = Depends(get_session),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    if alert.status == "ACKNOWLEDGED":
        return {"message": "Alert already acknowledged", "alert": alert}
        
    # User acknowledges alert (different from command ACK from device)
    alert.status = "ACKNOWLEDGED"
    session.add(alert)
    
    log_action(
        session=session,
        user_id=current_user.id,
        action="ACKNOWLEDGE_ALERT",
        entity_type="Alert",
        entity_id=str(alert.id),
        details={"alert_type": alert.alert_type}
    )
    
    session.commit()
    session.refresh(alert)
    
    return {"message": "Alert acknowledged successfully", "alert": alert}
