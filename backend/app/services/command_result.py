"""Read-time classification of unsent cancellations; dispatch/ACK state stays intact."""
from sqlalchemy import case, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB


def cancellation_status(command):
    children = list((command.dispatches or {}).values())
    if command.status != "FAILED" or not children:
        return None
    cancelled = [child for child in children if child.get("dispatch_state") == "CANCELLED"]
    if not cancelled or any(child.get("status") == "FAILED" and child.get("dispatch_state") != "CANCELLED"
                            for child in children):
        return None
    if len(cancelled) == len(children) and not any(child.get("publish_started_at") for child in children):
        return "CANCELLED"
    return "PARTIALLY_CANCELLED"


def cancellation_predicates(dispatches, status):
    """Same classification in PostgreSQL, without loading dispatch payloads into Python."""
    payload = cast(dispatches, JSONB)
    safe = case((func.jsonb_typeof(payload) == "object", payload), else_=cast(literal("{}"), JSONB))
    entries = func.jsonb_each(safe).table_valued("key", "value").alias()
    child = cast(entries.c.value, JSONB)
    state = func.coalesce(child["dispatch_state"].astext, "")
    any_cancelled = select(1).select_from(entries).where(state == "CANCELLED").exists()
    actual_failure = select(1).select_from(entries).where(child["status"].astext == "FAILED", state != "CANCELLED").exists()
    other_work = select(1).select_from(entries).where(or_(state != "CANCELLED", child["publish_started_at"].astext.is_not(None))).exists()
    cancelled = (status == "FAILED") & any_cancelled & ~actual_failure
    return cancelled & ~other_work, cancelled & other_work
