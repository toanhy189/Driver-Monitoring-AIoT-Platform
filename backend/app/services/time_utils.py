from datetime import datetime, timezone


def as_utc(value: datetime | None) -> datetime | None:
    """Database TIMESTAMP columns store UTC without a timezone marker."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
