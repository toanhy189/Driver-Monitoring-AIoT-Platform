from sqlmodel import Session
from app.models.audit_log import AuditLog

def log_action(
    session: Session,
    user_id: int,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None
):
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details
    )
    session.add(audit_log)
    # Note: caller is expected to call session.commit()
