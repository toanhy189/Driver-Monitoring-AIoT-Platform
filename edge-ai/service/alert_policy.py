"""Agreed bench policy. Timers use monotonic time; event dates use UTC."""

from datetime import datetime, timezone
import math
import time
import uuid

POLICY_VERSION = "driver-bench-20261107-v1"
LEVELS = ((3.0, 1, 1000, ("led", "buzzer")),
          (6.0, 2, 2000, ("led", "buzzer", "motor")),
          (10.0, 3, 3000, ("led", "buzzer", "motor")))
RISK = {"DROWSY", "DISTRACTED"}


class AlertPolicy:
    def __init__(self, device_code, model_version, clock=time.monotonic,
                 utcnow=lambda: datetime.now(timezone.utc), max_gap=0.5):
        self.device_code, self.model_version = device_code, model_version
        self.clock, self.utcnow, self.max_gap = clock, utcnow, max_gap
        self.session_id = str(uuid.uuid4())
        self.session_started_at = self.utcnow().isoformat()
        self.sequence = 0
        self.state = None
        self.candidate = None
        self.candidate_since = None
        self.episode_id = None
        self.episode_start_event_id = None
        self.clip_message_id = None
        self.risk_since = None
        self.level = 0
        self.last_warning = None
        self.last_observation = None
        self.observed_at = None
        self.last_update = None
        self.unknown_since = None
        self.last_fault = None
        self.suspended = False
        self.ended = False

    def event(self, kind, **fields):
        result = dict(message_id=str(uuid.uuid4()), device_code=self.device_code,
                      session_id=self.session_id, session_started_at=self.session_started_at,
                      episode_id=self.episode_id, episode_start_event_id=self.episode_start_event_id,
                      clip_message_id=self.clip_message_id,
                      sequence_number=self.sequence, timestamp=self.utcnow().isoformat(),
                      observed_at=self.observed_at, model_version=self.model_version,
                      policy_version=POLICY_VERSION, event_type=kind, state=self.state,
                      **fields)
        self.sequence += 1
        return result

    def update(self, candidate, valid=True, now=None, observed_at=None):
        if self.ended:
            return []
        now = self.clock() if now is None else now
        if not math.isfinite(now) or (self.last_update is not None and now < self.last_update):
            raise ValueError("Policy clock must be finite and monotonic")
        gap = self.last_update is not None and now - self.last_update > self.max_gap
        self.last_update = now
        events = []
        if gap:
            # A delayed loop never emits all missed thresholds or repeats in a burst.
            valid = False
        if not valid or candidate not in RISK | {"ATTENTIVE"}:
            candidate = "UNKNOWN"
        else:
            self.last_observation = now
            self.observed_at = observed_at or self.utcnow().isoformat()
        if candidate != self.candidate:
            self.candidate, self.candidate_since = candidate, now

        if candidate == "UNKNOWN":
            if self.unknown_since is None:
                self.unknown_since = now
            self.risk_since = None
            if self.state != "UNKNOWN":
                events.append(self.event("STATE_CHANGED", previous_state=self.state,
                                         next_state="UNKNOWN", end_reason="OBSERVATION_INTERRUPTED"))
                events[-1]["state"] = "UNKNOWN"
                self.clip_message_id = events[-1]["message_id"]
                events[-1]["clip_message_id"] = self.clip_message_id
                self.state = "UNKNOWN"
                self.episode_id = self.episode_start_event_id = None
                self.level, self.last_warning = 0, None
            self.suspended = True
            if now - self.unknown_since >= 2 and (self.last_fault is None or now - self.last_fault >= 30):
                events.append(self.event("MONITORING_FAULT", reason="DRIVER_NOT_OBSERVABLE"))
                self.last_fault = now
            return events

        self.unknown_since, self.last_fault = None, None
        if candidate != self.state and self.state in RISK and not self.suspended:
            events.append(self.event("RISK_SUSPENDED", reason="CANDIDATE_CHANGED",
                                     candidate_state=candidate))
            self.suspended = True
            self.risk_since = None
        confirm = {"ATTENTIVE": 2.0, "DROWSY": 0.5, "DISTRACTED": 0.3}[candidate]
        if candidate != self.state and now - self.candidate_since < confirm:
            return events
        if candidate != self.state:
            previous = self.state
            if candidate in RISK:
                self.episode_id = str(uuid.uuid4())
                self.episode_start_event_id = None
                self.risk_since = now
                self.level, self.last_warning = 0, None
            self.state = candidate
            changed = self.event("STATE_CHANGED", previous_state=previous,
                                 end_reason="RECOVERED" if candidate == "ATTENTIVE" else None)
            if candidate in RISK:
                self.episode_start_event_id = changed["message_id"]
                changed["episode_start_event_id"] = changed["message_id"]
            events.append(changed)
            self.clip_message_id = changed["message_id"]
            changed["clip_message_id"] = changed["message_id"]
            if candidate == "ATTENTIVE":
                self.episode_id = self.episode_start_event_id = None
                self.risk_since = None
                self.level, self.last_warning = 0, None
            self.suspended = False
        elif self.suspended and candidate in RISK:
            # Same unresolved episode, but continuous duration starts again.
            self.risk_since = now
            self.suspended = False
        if candidate not in RISK or self.suspended:
            return events
        if self.risk_since is None:
            self.risk_since = now
        duration = now - self.risk_since
        reached = [item for item in LEVELS if duration + 1e-8 >= item[0]]
        if not reached:
            return events
        _, level, milliseconds, outputs = reached[-1]
        if level > self.level or (level == self.level == 3 and
                                  self.last_warning is not None and now - self.last_warning >= 5):
            repeated = level == self.level
            self.level, self.last_warning = level, now
            events.append(self.event(f"{candidate}_THRESHOLD_REACHED", level=level,
                state_duration_ms=round(duration * 1000), repeat=repeated,
                duration_ms=milliseconds, outputs=list(outputs)))
        return events

    def end(self):
        if self.ended:
            return None
        self.ended = True
        return self.event("SESSION_ENDED", final_state=self.state or "UNKNOWN")

    def rotate_clip(self):
        event = self.event("STATE_CHANGED", previous_state=self.state, reason="CLIP_ROTATED")
        self.clip_message_id = event["message_id"]
        event["clip_message_id"] = event["message_id"]
        return event
