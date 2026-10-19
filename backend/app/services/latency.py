from datetime import datetime, timezone


def elapsed_ms(start, end):
    if not start or not end:
        return None
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00")).replace(tzinfo=None)
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00")).replace(tzinfo=None)
    return round(max(0, (end - start).total_seconds() * 1000), 3)


def command_latency(command):
    return {
        "http_ms": command.http_duration_ms,
        "total_to_completed_ms": elapsed_ms(command.created_at, command.completed_ack_at),
        "dispatches": {key: {
            "mqtt_publish_ms": child.get("publish_ms"),
            "ack_from_publish_ms": elapsed_ms(child.get("publish_started_at"), child.get("completed_ack_at")),
            "publish_started_at": child.get("publish_started_at"),
            "published_at": child.get("published_at"),
            "first_ack_at": child.get("first_ack_at"),
            "completed_ack_at": child.get("completed_ack_at"),
        } for key, child in (command.dispatches or {}).items()},
        "clock": "backend_utc",
    }
