"""Versioned bench policy; the source-device row is locked by the caller."""

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.core.config import settings
from app.models.ai_event import RuleBinding, RuleRuntime
from app.models.alert import Alert
from app.models.command import Command
from app.models.device import Device
from app.services.command_dispatch import create_command
from app.services.command_state import aggregate, update_dispatch

VERSION = "driver-bench-20261107-v1"
RISK = {"DROWSY", "DISTRACTED"}


def naive(date):
    return date.astimezone(timezone.utc).replace(tzinfo=None)


def cancel_unsent(session, source_id, session_id, episode_id=None):
    commands = session.exec(select(Command).where(Command.action == "AUTO_ALERT",
                            Command.status.in_(["PENDING", "SENT", "ACKNOWLEDGED"]))).all()
    for command in commands:
        changed = False
        for key, child in (command.dispatches or {}).items():
            guard = child.get("policy_guard", {})
            if (child.get("dispatch_state") == "QUEUED" and guard.get("source_device_id") == source_id
                    and guard.get("session_id") == session_id
                    and (episode_id is None or guard.get("episode_id") == episode_id)):
                command.dispatches = update_dispatch(command.dispatches, key, "FAILED", "Risk episode no longer actionable")
                command.dispatches = {**command.dispatches, key: {
                    **command.dispatches[key], "dispatch_state": "CANCELLED"}}
                changed = True
        if changed:
            aggregate(command)
            session.add(command)


def process_versioned_event(session, source, event, data, payload, now):
    notifications = []
    def outcome(value):
        event.outcome = value
        return list(notifications)

    if data.policy_version != VERSION:
        return outcome("UNKNOWN_POLICY")
    if source.lifecycle_state != "ACTIVE":
        return outcome("SOURCE_UNAVAILABLE")
    delivery = payload.get("_delivery")
    if not isinstance(delivery, dict) or delivery.get("mode") != "live":
        return outcome("BACKFILL_RECORDED")
    age = (now - event.occurred_at).total_seconds()
    if not 0 <= age <= 5:
        return outcome("STALE_RECORDED")
    runtime = session.get(RuleRuntime, source.id)
    current = dict(runtime.state) if runtime else {}
    started = naive(data.session_started_at)
    if started > now:
        return outcome("FUTURE_SESSION")
    if current.get("session_id") != data.session_id:
        if current and started <= datetime.fromisoformat(current["session_started_at"]):
            return outcome("OLD_SESSION")
        if current:
            cancel_unsent(session, source.id, current["session_id"])
        current = {"session_id": data.session_id, "session_started_at": started.isoformat(),
                   "sequence": -1, "ended": False, "episode_id": None, "level": 0}
    if data.sequence_number <= current.get("sequence", -1):
        return outcome("OLD_SEQUENCE")
    if current.get("ended"):
        return outcome("SESSION_ALREADY_ENDED")
    current["sequence"] = data.sequence_number
    if data.observed_at is not None and 0 <= (now - naive(data.observed_at)).total_seconds() <= 2:
        current["last_observed_at"] = naive(data.observed_at).isoformat()
        current["monitoring_state"] = data.state
    if runtime is None:
        runtime = RuleRuntime(source_device_id=source.id, state=current)

    def persist(value):
        runtime.state = dict(current)
        session.add(runtime)
        return outcome(value)

    if payload.get("reason") == "CLIP_ROTATED":
        return persist("CLIP_RECORDED")
    if (data.event_type == "STATE_CHANGED" and data.state in RISK | {"ATTENTIVE"}
            and data.observed_at is not None and 0 <= (now-naive(data.observed_at)).total_seconds() <= 2
            and current.get("fault_alert_id")):
        fault = session.get(Alert, current.pop("fault_alert_id"))
        if fault:
            fault.status = "RESOLVED"
            session.add(fault)
            notifications.append({"type": "alert.updated", "data": {"device_id": source.id,
                "device_code": source.device_code, "alert_id": fault.id, "status": "RESOLVED"}})

    if data.event_type in {"SESSION_ENDED", "RISK_SUSPENDED"} or (
            data.event_type == "STATE_CHANGED" and data.state not in RISK):
        cancel_unsent(session, source.id, data.session_id)
        current["supported"] = False
        if data.event_type == "SESSION_ENDED":
            current["ended"] = True
        elif data.event_type == "STATE_CHANGED":
            current["state"] = data.state
            current["episode_id"] = None
            if data.state == "ATTENTIVE" and current.get("alert_id"):
                alert = session.get(Alert, current["alert_id"])
                if alert:
                    alert.status = "RESOLVED"
                    session.add(alert)
        return persist("SESSION_CLOSED" if current.get("ended") else "RISK_SUSPENDED")

    if data.event_type == "MONITORING_FAULT":
        created = False
        if not current.get("fault_alert_id"):
            alert = Alert(device_id=source.id, alert_type="MONITORING_FAULT", status="NEW",
                          source_event_id=data.event_id, description="Driver monitoring unavailable")
            session.add(alert)
            session.flush()
            current["fault_alert_id"] = alert.id
            created = True
        persist("MONITORING_FAULT_RECORDED")
        return [{"type": "alert.created" if created else "alert.updated", "data": {
            "device_id": source.id, "device_code": source.device_code,
            "alert_id": current["fault_alert_id"], "alert_type": "MONITORING_FAULT",
            "event_id": data.event_id, "status": "NEW"}}]

    if data.state not in RISK or not data.episode_id:
        return persist("RECORDED")
    if data.observed_at is None or not 0 <= (now - naive(data.observed_at)).total_seconds() <= 2:
        return persist("STALE_OBSERVATION")
    if current.get("episode_id") != data.episode_id:
        cancel_unsent(session, source.id, data.session_id)
        current.update(episode_id=data.episode_id, state=data.state, level=0,
                       alert_id=None, last_command_at=None)
    elif current.get("state") != data.state:
        return persist("EPISODE_STATE_MISMATCH")
    current["supported"] = True
    if data.event_type == "STATE_CHANGED":
        return persist("EPISODE_STARTED")
    level = max((number for number, threshold in ((1, 3000), (2, 6000), (3, 10000))
                 if data.state_duration_ms >= threshold), default=0)
    if level == 0 or data.level != level:
        return persist("INVALID_LEVEL")
    prior_level = current.get("level", 0)
    if level < prior_level or (level == prior_level and level != 3):
        return persist("LEVEL_ALREADY_HANDLED")

    def record_without_command(reason):
        # A disabled rule/offline actuator must not hide a fresh driver warning.
        alert = session.get(Alert, current["alert_id"]) if current.get("alert_id") else None
        created = alert is None
        if created:
            alert = Alert(device_id=source.id, alert_type=data.event_type, status="NEW",
                source_event_id=data.event_id, severity=str(level), created_at=event.occurred_at,
                description=f"episode={data.episode_id}; policy={VERSION}")
            session.add(alert)
            session.flush()
            current["alert_id"] = alert.id
        alert.severity = str(max(int(alert.severity or 0), level))
        session.add(alert)
        notifications.append({"type": "alert.created" if created else "alert.updated", "data": {
            "alert_id": alert.id, "device_id": source.id, "device_code": source.device_code,
            "event_id": data.event_id, "episode_id": data.episode_id, "alert_type": alert.alert_type,
            "severity": int(alert.severity), "status": alert.status, "rule_outcome": reason}})
        return persist(reason)

    binding = session.get(RuleBinding, source.id)
    if not (settings.RULE_ENGINE_ENABLED and binding and binding.enabled):
        return record_without_command("RULE_DISABLED")
    if binding.policy.get("policy_version") != VERSION:
        return record_without_command("POLICY_MISMATCH")
    if event.occurred_at < binding.updated_at or naive(data.observed_at) < binding.updated_at:
        return record_without_command("PRE_BINDING_EVENT")
    target = session.get(Device, binding.target_device_id)
    if (target is None or target.device_type != "ALERT_NODE" or target.lifecycle_state != "ACTIVE"
            or target.status != "ONLINE" or target.last_seen is None
            or not 0 <= (now-target.last_seen).total_seconds() <= 90):
        return record_without_command("TARGET_UNAVAILABLE")
    if level == prior_level == 3 and current.get("last_command_at") and (
            now-datetime.fromisoformat(current["last_command_at"])).total_seconds() < 5:
        return persist("REPEAT_TOO_EARLY")
    alert = session.get(Alert, current["alert_id"]) if current.get("alert_id") else None
    created = alert is None
    if alert:
        commands = session.exec(select(Command).where(Command.alert_id == alert.id)).all()
        starts = [datetime.fromisoformat(child["publish_started_at"].removesuffix("Z"))
                  for command in commands for child in (command.dispatches or {}).values()
                  if child.get("publish_started_at")]
        if level == prior_level == 3 and starts and (now-max(starts)).total_seconds() < 5:
            return persist("REPEAT_TOO_EARLY")
        if any(child.get("dispatch_state") in {"QUEUED", "PUBLISHING", "PUBLISHED"}
               and child.get("status") not in {"COMPLETED", "FAILED"}
               and command.status != "TIMEOUT"
               for command in commands for child in (command.dispatches or {}).values()):
            return record_without_command("DISPATCH_UNRESOLVED")
    else:
        alert = Alert(device_id=source.id, alert_type=data.event_type, status="NEW",
                      source_event_id=data.event_id, severity=str(level), created_at=event.occurred_at,
                      description=f"episode={data.episode_id}; policy={VERSION}")
        session.add(alert)
        session.flush()
        current["alert_id"] = alert.id
    alert.severity = str(level)
    session.add(alert)
    duration = {1: 1000, 2: 2000, 3: 3000}[level]
    intensity = {1: "WEAK", 2: "MEDIUM", 3: "STRONG"}[level]
    expires = min(event.occurred_at + timedelta(seconds=5), naive(data.observed_at) + timedelta(seconds=2))
    actions = {key: {"command": name, "duration": duration, "intensity": intensity,
                     "expires_at_ms": int(expires.replace(tzinfo=timezone.utc).timestamp()*1000)}
               for key, name in (("led", "LED_ON"), ("buzzer", "BUZZER_ON"), ("motor", "MOTOR_ON"))
               if level > 1 or key != "motor"}
    command = create_command(session, target, "AUTO_ALERT", actions, alert_id=alert.id)
    guard = {"source_device_id": source.id, "session_id": data.session_id,
             "target_device_id": target.id,
             "binding_revision": binding.updated_at.isoformat(timespec="microseconds"),
             "episode_id": data.episode_id, "event_id": data.event_id,
             "expires_at": expires.isoformat()}
    command.dispatches = {key: {**child, "policy_guard": guard} for key, child in command.dispatches.items()}
    session.add(command)
    current.update(level=level, last_command_at=now.isoformat())
    persist("QUEUED")
    return [*notifications, {"type": "alert.created" if created else "alert.updated", "data": {
                "alert_id": alert.id, "device_id": source.id, "device_code": source.device_code,
                "event_id": data.event_id, "episode_id": data.episode_id,
                "alert_type": alert.alert_type, "severity": level, "status": alert.status,
                "rule_outcome": event.outcome}},
            {"type": "command.updated", "data": {"request_id": command.request_id,
                "device_id": target.id, "action": command.action, "status": command.status,
                "alert_id": alert.id, "event_id": data.event_id}}]


def guard_is_valid(session, guard, now, target_device_id=None):
    source = session.exec(select(Device).where(Device.id == guard["source_device_id"])
                          .execution_options(populate_existing=True)).first()
    runtime = session.exec(select(RuleRuntime).where(
        RuleRuntime.source_device_id == guard["source_device_id"]).execution_options(populate_existing=True)).first()
    binding = session.exec(select(RuleBinding).where(
        RuleBinding.source_device_id == guard["source_device_id"]).execution_options(populate_existing=True)).first()
    state = runtime.state if runtime else {}
    return (settings.RULE_ENGINE_ENABLED and binding and binding.enabled and binding.policy.get("policy_version") == VERSION
            and source and source.lifecycle_state == "ACTIVE"
            and binding.target_device_id == guard.get("target_device_id")
            and (target_device_id is None or binding.target_device_id == target_device_id)
            and binding.updated_at.isoformat(timespec="microseconds") == guard.get("binding_revision")
            and state.get("session_id") == guard.get("session_id") and not state.get("ended")
            and state.get("episode_id") == guard.get("episode_id") and state.get("supported")
            and now <= datetime.fromisoformat(guard["expires_at"]))
