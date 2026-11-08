"""Keep missing observations out of eye, head and event duration counters."""

import time


class ObservationContinuity:
    def __init__(self, eyes, perclos, head, state_data, reset_seconds=1.0,
                 max_gap_seconds=0.5):
        self.eyes = eyes
        self.perclos = perclos
        self.head = head
        self.state = state_data
        self.reset_seconds = reset_seconds
        self.max_gap_seconds = max_gap_seconds
        self.last_seen = None
        self.missing_since = None
        self.window_reset = False

    def update(self, present, now=None):
        now = time.monotonic() if now is None else now
        delayed = self.last_seen is not None and now - self.last_seen > self.max_gap_seconds
        interrupted = not present or delayed or self.missing_since is not None
        if not interrupted:
            self.last_seen = now
            return False

        if self.missing_since is None:
            self.missing_since = self.last_seen if self.last_seen is not None else now
            self.eyes.reset()
            self.perclos.interrupt()
            self.head.interrupt()
            self.state["candidate_state"] = "UNKNOWN"
            self.state["candidate_since"] = now
            for state in self.state["threshold_since"]:
                self.state["threshold_since"][state] = None
                self.state["threshold_event_sent"][state] = False

        if not self.window_reset and now - self.missing_since >= self.reset_seconds:
            self.perclos.reset()
            self.window_reset = True

        if present:
            self.last_seen = now
            self.missing_since = None
            self.window_reset = False
        return True
