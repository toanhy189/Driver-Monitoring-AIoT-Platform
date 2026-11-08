"""Optional temporal eye-closure evidence, independent of the RF window.

This detects measured prolonged eye closure, not medically verified drowsiness.
The caller must supply missing EAR when the current observation is unavailable.
"""

import math


class EyeClosureGuard:
    VERSION = "eye-closure-guard-v1"

    def __init__(self, ear_threshold=0.20, closed_seconds=1.0,
                 recovery_seconds=1.0, max_gap_seconds=0.5):
        values = (ear_threshold, closed_seconds, recovery_seconds, max_gap_seconds)
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Eye closure guard settings must be finite and positive")
        self.ear_threshold = ear_threshold
        self.closed_seconds = closed_seconds
        self.recovery_seconds = recovery_seconds
        self.max_gap_seconds = max_gap_seconds
        self.reset()

    def reset(self):
        self.active = False
        self.closed_since = self.open_since = self.last_update = None

    def update(self, now, ear=None):
        now = float(now)
        if not math.isfinite(now) or (self.last_update is not None and now < self.last_update):
            self.reset()
            raise ValueError("Eye closure guard clock must be finite and monotonic")
        if ear is None or not math.isfinite(ear) or ear < 0:
            self.reset()
            return False
        if self.last_update is not None and now - self.last_update > self.max_gap_seconds:
            self.reset()
        self.last_update = now
        if ear < self.ear_threshold:
            self.open_since = None
            if self.closed_since is None:
                self.closed_since = now
            if now - self.closed_since + 1e-8 >= self.closed_seconds:
                self.active = True
        else:
            self.closed_since = None
            if self.open_since is None:
                self.open_since = now
            if now - self.open_since + 1e-8 >= self.recovery_seconds:
                self.active = False
        return self.active
