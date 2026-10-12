import secrets
import threading
import time


_tickets: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()
TTL_SECONDS = 30


def issue_ticket(user_id: int) -> str:
    ticket = secrets.token_urlsafe(32)
    with _lock:
        now = time.monotonic()
        for key, (_, expiry) in list(_tickets.items()):
            if expiry < now:
                del _tickets[key]
        _tickets[ticket] = (user_id, now + TTL_SECONDS)
    return ticket


def consume_ticket(ticket: str) -> int | None:
    with _lock:
        item = _tickets.pop(ticket, None)
    if item is None or item[1] < time.monotonic():
        return None
    return item[0]
