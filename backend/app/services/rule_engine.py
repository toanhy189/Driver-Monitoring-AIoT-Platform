"""One database transaction links an AI event, alert and queued command."""

import hashlib
import json
import logging
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.models.ai_event import AiEvent, RuleBinding
from app.models.alert import Alert
from app.models.device import Device
from app.schemas.rules import AiEventRequest, RulePolicy
from app.services.command_dispatch import create_command
from app.services.time_utils import as_utc


logger = logging.getLogger(__name__)


def process_event(session: Session, payload: dict) -> list[dict]:
    try:
        data = AiEventRequest.model_validate(payload)
    except ValidationError:
        logger.warning("Ignoring invalid AI event schema")
        return []
    source = session.exec(select(Device).where(Device.device_code == data.device_id)
                          .with_for_update()).first()
    if source is None or source.device_type != "VISION_NODE" or source.lifecycle_state == "DECOMMISSIONED":
        return []
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = session.exec(select(AiEvent).where(AiEvent.event_id == data.event_id)).first()
    if existing:
        if existing.payload_hash != digest or existing.device_id != source.id:
            logger.warning("AI event ID reused with different content: %s", data.event_id)
        return []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    event = AiEvent(event_id=data.event_id, device_id=source.id, event_type=data.event_type,
                    occurred_at=data.timestamp.astimezone(timezone.utc).replace(tzinfo=None),
                    received_at=now, model_version=data.model_version, state=data.state,
                    state_duration_ms=data.state_duration_ms, payload_hash=digest, payload=payload)
    session.add(event)
    try:
        session.flush()
        if data.event_type == "STATE_CHANGED":
            session.commit()
            return []
        if session.exec(select(Alert).where(Alert.source_event_id == data.event_id)).first():
            event.outcome = "LEGACY_DUPLICATE"
            session.add(event)
            session.commit()
            return []
        binding = session.exec(select(RuleBinding).where(RuleBinding.source_device_id == source.id)
                               .with_for_update()).first()
        policy = RulePolicy.model_validate(binding.policy) if binding else RulePolicy()
        severity = max((level for level in (1, 2, 3)
                        if data.state_duration_ms >= policy.levels[str(level)].threshold_ms), default=0)
        enabled = settings.RULE_ENGINE_ENABLED and binding is not None and binding.enabled
        if severity == 0:
            event.outcome = "BELOW_THRESHOLD"
            session.add(event)
            session.commit()
            return []
        if enabled and binding.last_triggered_at and \
                (now - binding.last_triggered_at).total_seconds() < policy.cooldown_seconds:
            event.outcome = "COOLDOWN_SUPPRESSED"
            session.add(event)
            session.commit()
            return []
        alert = Alert(device_id=source.id, alert_type=data.event_type, status="NEW",
                      source_event_id=data.event_id, severity=str(severity), created_at=event.occurred_at)
        session.add(alert)
        session.flush()
        event.outcome = "RULE_DISABLED"
        command = None
        age = (now - event.occurred_at).total_seconds()
        if enabled:
            target = session.get(Device, binding.target_device_id)
            fresh = target and target.last_seen and 0 <= (now - target.last_seen).total_seconds() <= 90
            if not -5 <= age <= policy.max_event_age_seconds:
                event.outcome = "STALE_RECORDED"
            elif not target or target.device_type != "ALERT_NODE" or \
                    target.lifecycle_state != "ACTIVE" or target.status != "ONLINE" or not fresh:
                event.outcome = "TARGET_UNAVAILABLE"
            else:
                intensity = {1: "WEAK", 2: "MEDIUM", 3: "STRONG"}[severity]
                duration = policy.levels[str(severity)].duration_ms
                actions = {key: {"command": name, "duration": duration, "intensity": intensity}
                           for key, name in (("led", "LED_ON"), ("buzzer", "BUZZER_ON"), ("motor", "MOTOR_ON"))
                           if key in policy.levels[str(severity)].outputs}
                command = create_command(session, target, "AUTO_ALERT", actions, alert_id=alert.id)
                event.outcome = "QUEUED"
            binding.last_triggered_at = now
            session.add(binding)
        session.add(event)
        session.commit()
        result = [{"type": "alert.created", "data": {
            "alert_id": alert.id, "device_id": source.id, "device_code": source.device_code,
            "event_id": event.event_id,
            "alert_type": alert.alert_type, "severity": severity, "status": alert.status,
            "created_at": as_utc(alert.created_at).isoformat(), "rule_outcome": event.outcome,
        }}]
        if command:
            result.append({"type": "command.updated", "data": {
                "request_id": command.request_id, "device_id": command.device_id,
                "action": command.action, "status": command.status, "alert_id": alert.id,
                "event_id": event.event_id,
            }})
        return result
    except IntegrityError:
        session.rollback()
        logger.info("Concurrent AI event delivery ignored: %s", data.event_id)
        return []
