"""Readiness and cancellation for the camera -> actuator link. Never publishes MQTT."""
from datetime import datetime, timezone

from sqlmodel import select

from app.core.config import settings
from app.models.ai_event import RuleBinding, RuleRuntime
from app.models.alert import Alert
from app.models.command import Command
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.services.ai_policy import VERSION
from app.services.command_state import aggregate, update_dispatch


def revision(binding):
    return binding.updated_at.isoformat(timespec="microseconds") if binding else None


def source_commands(session, source_id, *, lock=False):
    query = select(Command).join(Alert, Command.alert_id == Alert.id).where(
        Command.action == "AUTO_ALERT", Alert.device_id == source_id,
    ).order_by(Command.id)
    if lock:
        # ACKs update the whole dispatch JSON too. Read the latest locked row
        # before cancelling siblings so a concurrent completed ACK is retained.
        query = query.with_for_update(of=Command).execution_options(populate_existing=True)
    return session.exec(query).all()


def cancel_binding_commands(session, source_id):
    """Keep published work and manual commands; cancel only unsent automatic children."""
    for command in source_commands(session, source_id, lock=True):
        changed = False
        for key, child in list((command.dispatches or {}).items()):
            if child.get("dispatch_state") != "QUEUED" or child.get("status") in {"COMPLETED", "FAILED"}:
                continue
            command.dispatches = update_dispatch(command.dispatches, key, "FAILED", "Warning link changed or disabled")
            command.dispatches = {**command.dispatches, key: {
                **command.dispatches[key], "dispatch_state": "CANCELLED"}}
            changed = True
        if changed:
            aggregate(command)
            session.add(command)


def has_inflight_commands(session, source_id):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return any(
        child.get("dispatch_state") in {"PUBLISHING", "PUBLISHED"}
        and child.get("status") not in {"COMPLETED", "FAILED"}
        and command.status != "TIMEOUT"
        # Cancelling queued siblings can make the parent FAILED while another
        # child still awaits ACK. Bound that wait by the normal command timeout.
        and (now - command.created_at).total_seconds() < settings.COMMAND_TIMEOUT_SECONDS
        for command in source_commands(session, source_id)
        for child in (command.dispatches or {}).values()
    )


def active_source_for_target(session, target_id, except_source_id):
    return session.exec(select(RuleBinding.source_device_id).join(
        Device, Device.id == RuleBinding.source_device_id).where(
        RuleBinding.target_device_id == target_id,
        RuleBinding.source_device_id != except_source_id,
        RuleBinding.enabled.is_(True), Device.lifecycle_state != "DECOMMISSIONED",
    )).first()


def device_summary(device):
    return {key: getattr(device, key) for key in (
        "id", "device_code", "name", "status", "lifecycle_state", "last_seen", "device_type")}


def binding_status(session, source, binding, now=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    target = session.get(Device, binding.target_device_id) if binding else None
    runtime = session.get(RuleRuntime, source.id)
    state = runtime.state if runtime else {}
    blockers = []
    if binding is None:
        blockers.append("UNBOUND")
    elif not binding.enabled:
        blockers.append("DISABLED")
    if not settings.RULE_ENGINE_ENABLED:
        blockers.append("ENGINE_DISABLED")
    if binding and binding.policy.get("policy_version") != VERSION:
        blockers.append("POLICY_MISMATCH")
    if source.lifecycle_state != "ACTIVE":
        blockers.append("SOURCE_INACTIVE")
    if binding and (target is None or target.lifecycle_state != "ACTIVE" or target.device_type != "ALERT_NODE"):
        blockers.append("TARGET_INACTIVE")
    elif target and (target.status != "ONLINE" or target.last_seen is None
                     or not 0 <= (now - target.last_seen).total_seconds() <= 90):
        blockers.append("TARGET_OFFLINE")
    # Telemetry continues while ATTENTIVE; state-change events alone would make
    # a healthy camera appear idle between transitions. Backfilled telemetry
    # keeps its old recorded_at and therefore cannot indicate readiness.
    telemetry = session.exec(select(Telemetry).where(Telemetry.device_id == source.id)
        .order_by(Telemetry.recorded_at.desc(), Telemetry.id.desc()).limit(1)).first()
    observed = state.get("last_observed_at")
    observed_at = datetime.fromisoformat(observed) if observed else None
    observation_state = state.get("monitoring_state", state.get("state"))
    if telemetry and (observed_at is None or telemetry.recorded_at > observed_at):
        observed_at = telemetry.recorded_at
        observation_state = telemetry.driver_state
    if state.get("ended"):
        blockers.append("SESSION_ENDED")
    elif observation_state == "UNKNOWN":
        blockers.append("MONITORING_UNAVAILABLE")
    elif observed_at is None or not 0 <= (now - observed_at).total_seconds() <= 2:
        blockers.append("WAITING_FOR_AI")
    # This describes configuration and recent observations, not a promise that
    # the next event will actuate: expiry, sequence and pending ACKs are rechecked.
    return {"ready": not blockers, "blockers": blockers,
            "target": device_summary(target) if target else None,
            "last_observed_at": observed_at, "inflight": has_inflight_commands(session, source.id)}
