from datetime import datetime, timezone


RANK = {
    "PENDING": 0,
    "SENT": 1,
    "ACKNOWLEDGED": 2,
    "STARTED": 2,
    "COMPLETED": 3,
    "FAILED": 3,
}


def update_dispatch(dispatches: dict, key: str, status: str, error: str | None = None) -> dict:
    current = dispatches[key]
    if RANK.get(status, -1) < RANK.get(current["status"], -1):
        return dispatches
    if current["status"] in {"COMPLETED", "FAILED"}:
        return dispatches
    result = {name: dict(value) for name, value in dispatches.items()}
    result[key]["status"] = status
    if error:
        result[key]["error"] = error
    return result


def aggregate(command) -> None:
    states = [item["status"] for item in (command.dispatches or {}).values()]
    if not states:
        return
    if "FAILED" in states:
        command.status = "FAILED"
        command.ack_status = "FAILED"
        command.error_message = next(
            (item.get("error") for item in command.dispatches.values() if item["status"] == "FAILED"),
            "Device reported a failed action",
        )
        command.executed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif all(state == "COMPLETED" for state in states):
        command.status = "ACKNOWLEDGED"
        command.ack_status = "COMPLETED"
        command.error_message = None
        command.executed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif any(state in {"ACKNOWLEDGED", "STARTED", "COMPLETED"} for state in states):
        command.status = "ACKNOWLEDGED"
        command.ack_status = "ACCEPTED"
    elif all(state == "SENT" for state in states):
        command.status = "SENT"
    else:
        command.status = "PENDING"
