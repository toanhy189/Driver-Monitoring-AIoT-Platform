"""Play an on-device warning without waiting for MQTT, HTTP or a camera loop."""

import logging
import sys
import threading
import time
from datetime import datetime, timezone

from config import LOCAL_ALERT_ENABLED, LOCAL_ALERT_COOLDOWN_SECONDS

logger = logging.getLogger(__name__)


def play_policy_warning(event, stopped):
    state = event["state"]
    duration = event.get("duration_ms", 350)/1000
    until = time.monotonic() + min(3, duration)
    while not stopped.is_set() and time.monotonic() < until:
        play_warning(state)
        if stopped.wait(0.1):
            break


def play_warning(state):
    if sys.platform == "win32":
        import winsound
        winsound.Beep({"DROWSY": 1400, "DISTRACTED": 1000, "UNKNOWN": 650}[state], 350)
    else:
        # Terminal bell is a best-effort fallback; verify audio on the target machine.
        sys.stdout.write("\a")
        sys.stdout.flush()


class LocalAlertWorker:
    def __init__(self, enabled=LOCAL_ALERT_ENABLED, cooldown=LOCAL_ALERT_COOLDOWN_SECONDS,
                 player=None):
        self.enabled = enabled
        self.cooldown = cooldown
        self.player = player or play_warning
        self.policy_player = player is None
        self.last_alert_at = None
        self.pending = None
        self.seen = set()
        self.lock = threading.Lock()
        self.wakeup = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="local-alert")

    def start(self):
        if self.enabled:
            self.thread.start()

    def notify(self, event):
        if not self.enabled or self.stopped.is_set():
            return False
        state = event.get("state")
        fresh_remaining = 2.0
        if event.get("policy_version") and state in {"DROWSY", "DISTRACTED"}:
            try:
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(event["observed_at"])).total_seconds()
                if not 0 <= age <= 2:
                    return False
                fresh_remaining = 2-age
            except (KeyError, TypeError, ValueError):
                return False
        if not ((state in {"DROWSY", "DISTRACTED"} and
                 event.get("event_type") == f"{state}_THRESHOLD_REACHED") or
                (state == "UNKNOWN" and event.get("event_type") == "MONITORING_FAULT")):
            return False
        now = time.monotonic()
        with self.lock:
            identity = event.get("message_id")
            if identity and identity in self.seen:
                return False
            # Policy already schedules escalation/repeats; a second cooldown must not block it.
            if not event.get("policy_version") and (self.pending is not None or (
                    self.last_alert_at is not None and now - self.last_alert_at < self.cooldown)):
                return False
            if len(self.seen) >= 1024:
                self.seen.clear()
            if identity:
                self.seen.add(identity)
            self.pending = (state, now + fresh_remaining, dict(event))
            self.last_alert_at = now
        self.wakeup.set()
        return True

    def cancel(self):
        """Discard queued audio on recovery, loss of observation or session end."""
        with self.lock:
            self.pending = None

    def _run(self):
        while not self.stopped.is_set():
            self.wakeup.wait()
            self.wakeup.clear()
            if self.stopped.is_set():
                break
            with self.lock:
                pending, self.pending = self.pending, None
            if pending is not None and time.monotonic() <= pending[1]:
                state = pending[0]
                try:
                    if self.policy_player and pending[2].get("policy_version"):
                        play_policy_warning(pending[2], self.stopped)
                    else:
                        self.player(state)
                    logger.info("Local warning: %s", state)
                except Exception as error:
                    logger.error("Local audio failed (%s); check the speaker", type(error).__name__)

    def stop(self):
        self.stopped.set()
        self.wakeup.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
