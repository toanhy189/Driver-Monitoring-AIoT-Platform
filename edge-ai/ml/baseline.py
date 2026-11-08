"""Replay the existing binary drowsiness candidate, before head-pose fusion.

Reuses PerclosCalculator, including its warmup/interrupt behavior. A video label
cannot validate head-pose distraction or the later event debounce/threshold.
"""

from eye import PerclosCalculator


class BaselineReplay:
    def __init__(self, config):
        self.config = config
        self.perclos = PerclosCalculator(config.ear_threshold, 10.0, 10.0,
                                        config.max_gap_seconds)
        self.last_seen = None
        self.missing_since = None
        self.eyes_open_since = None
        self.prediction = None

    def update(self, now, ear):
        delayed = self.last_seen is not None and now - self.last_seen > self.config.max_gap_seconds
        if ear is None or delayed or self.missing_since is not None:
            if self.missing_since is None:
                self.missing_since = self.last_seen if self.last_seen is not None else now
                self.perclos.interrupt()
                self.eyes_open_since = None
            if now - self.missing_since >= self.config.face_loss_reset_seconds:
                self.perclos.reset()
        if ear is None:
            self.prediction = None
            return None
        self.last_seen, self.missing_since = now, None
        value = self.perclos.update(ear, now=now)
        if ear < self.config.ear_threshold:
            self.eyes_open_since = None
        elif self.eyes_open_since is None:
            self.eyes_open_since = now
        recovered = self.eyes_open_since is not None and now - self.eyes_open_since >= 1.0
        self.prediction = None if value is None else int(value > 0.20 and not recovered)
        return self.prediction
