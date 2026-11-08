from sqlmodel import Session
from app.core.logging_config import correlation_id_context
from app.models.audit_log import AuditLog

# Audit truoc day nhan details tuy y; allowlist nay ngan payload/secret bi luu vao DB.
_SAFE_DETAIL_KEYS = {
    "ack_status",
    "alert_type",
    "config_id",
    "correlation_id",
    "device_code",
    "enabled",
    "from_state",
    "method",
    "path",
    "request_id",
    "result",
    "role",
    "size_bytes",
    "status",
    "target_device_id",
    "target_user_id",
    "to_state",
    "video_id",
}


def _safe_details(details: dict | None) -> dict | None:
    # Chi giu scalar co khoa duoc phe duyet va gioi han do dai chuoi metadata.
    if not details:
        return None
    return {
        key: value[:256] if isinstance(value, str) else value
        for key, value in details.items()
        if key in _SAFE_DETAIL_KEYS
        and (isinstance(value, (str, int, float, bool)) or value is None)
    }


def log_action(
    session: Session,
    user_id: int,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None
):
    # Chi them correlation ID khi audit phat sinh trong HTTP request.
    safe_details = _safe_details(details) or {}
    correlation_id = correlation_id_context.get()
    if correlation_id != "-":
        # Audit truoc day chua lien ket duoc voi HTTP log; them correlation ID neu co request.
        safe_details["correlation_id"] = correlation_id
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        # Audit truoc day nhan details tuy y; chi luu metadata da duoc phe duyet.
        details=safe_details or None,
    )
    session.add(audit_log)
    # Caller van chiu trach nhiem commit cung giao dich nghiep vu.
