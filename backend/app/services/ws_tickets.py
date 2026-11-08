import secrets
import threading
import time
from fastapi import HTTPException
from app.core.config import settings


_tickets: dict[str, tuple[int, int, float]] = {}
_lock = threading.Lock()
TTL_SECONDS = settings.WS_TICKET_TTL_SECONDS


def issue_ticket(user_id: int, session_version: int = 0) -> str:
    ticket = secrets.token_urlsafe(32)
    with _lock:
        now = time.monotonic()
        for key, (_, _, expiry) in list(_tickets.items()):
            if expiry < now:
                del _tickets[key]
        if len(_tickets) >= settings.MAX_WS_TICKETS:
            raise HTTPException(status_code=503, detail="WebSocket ticket capacity reached")
        _tickets[ticket] = (user_id, session_version, now + TTL_SECONDS)
    return ticket


def consume_ticket(ticket: str) -> int | None:
    item = consume_ticket_identity(ticket)
    return item[0] if item else None


def consume_ticket_identity(ticket: str) -> tuple[int, int] | None:
    with _lock:
        item = _tickets.pop(ticket, None)
    if item is None or item[2] < time.monotonic():
        return None
    return item[0], item[1]


def revoke_tickets(user_id: int):
    with _lock:
        for key, (owner, _, _) in list(_tickets.items()):
            if owner == user_id:
                del _tickets[key]
