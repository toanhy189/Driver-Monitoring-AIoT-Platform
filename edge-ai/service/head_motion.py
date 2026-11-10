"""Experimental head-motion observations. Never changes driver state or actuators.

Angles have a separate geometry/version from the legacy yaw/pitch RF inputs.
Thresholds are development settings, pending guided camera acceptance.
"""
from collections import deque
import math
import statistics

import numpy as np

VERSION = "head-motion-v1"
CONFIG = dict(calibration_seconds=3., calibration_spread_deg=4., down_deg=12.,
              return_deg=5., min_cycle_seconds=.5, min_lowered_seconds=.25,
              max_cycle_seconds=4., window_seconds=20., max_gap_seconds=.5,
              max_yaw_deg=25., max_roll_deg=20., max_down_deg=40., max_up_deg=15.)
CONFIG.update(reacquire_seconds=1., reacquire_neutral_deg=8.)


def rotation_angles(matrix):
    """Extract XYZ Euler angles from canonical-to-observed rotation, in degrees.

    Remove scale via SVD, reject degenerate/reflected/nonfinite matrices. Positive
    X rotation is the provisional down direction; validate on the actual camera.
    """
    try:
        m = np.asarray(matrix, dtype=float)
        if m.shape != (4, 4) or not np.isfinite(m).all():
            return None
        a = m[:3, :3]
        u, scales, vt = np.linalg.svd(a)
        if min(scales) < 1e-6 or max(scales)/min(scales) > 1.15:
            return None
        r = u @ vt
        if np.linalg.det(r) < .99:
            return None
        cy = math.hypot(r[0, 0], r[1, 0])
        if cy < .1:  # Euler singularity: do not turn it into a nod.
            return None
        return dict(pitch=math.degrees(math.atan2(r[2, 1], r[2, 2])),
                    yaw=math.degrees(math.atan2(-r[2, 0], cy)),
                    roll=math.degrees(math.atan2(r[1, 0], r[0, 0])))
    except (ValueError, TypeError, np.linalg.LinAlgError):
        return None


class HeadMotionTracker:
    def __init__(self):
        self.baseline = None
        self.calibration = deque()
        self.previous = None
        self.nods = deque(maxlen=100)
        self.departed_at = self.lowered_at = None
        self.armed = False
        self.reacquire_since = None

    def interrupt(self):
        self.nods.clear()
        self.calibration.clear()
        self.departed_at = self.lowered_at = None
        self.armed = False
        self.reacquire_since = None

    def snapshot(self, state="UNAVAILABLE", angles=None, eye_closed=False):
        count = len(self.nods) if state not in {"UNAVAILABLE", "CALIBRATING", "OUT_OF_RANGE", "REACQUIRING"} else 0
        return dict(version=VERSION, mode="OBSERVE_ONLY", available=state != "UNAVAILABLE",
                    calibrated=self.baseline is not None, state=state,
                    pitch_deg=angles["pitch"] if angles else None,
                    yaw_deg=angles["yaw"] if angles else None,
                    roll_deg=angles["roll"] if angles else None,
                    nod_count=count, repeated_nods=count >= 2,
                    eye_closure_supported=bool(count >= 2 and eye_closed))

    def update(self, now, angles, *, neutral_allowed=False, eye_closed=False):
        valid_time = isinstance(now, (int, float)) and not isinstance(now, bool) and math.isfinite(now)
        valid_angles = isinstance(angles, dict) and all(
            isinstance(angles.get(k), (int, float)) and not isinstance(angles[k], bool)
            and math.isfinite(angles[k]) and abs(angles[k]) <= 180 for k in ("pitch", "yaw", "roll"))
        backwards = valid_time and self.previous is not None and now <= self.previous
        gap = valid_time and self.previous is not None and now-self.previous > CONFIG["max_gap_seconds"]
        if valid_time and not backwards:
            self.previous = now
        if not valid_time or not valid_angles or backwards or gap:
            self.interrupt()
            return self.snapshot()
        if self.baseline is None:
            if not neutral_allowed:
                self.calibration.clear()
                return self.snapshot("CALIBRATING")
            self.calibration.append((now, dict(angles)))
            if any(max(a[k] for _, a in self.calibration)-min(a[k] for _, a in self.calibration)
                   > CONFIG["calibration_spread_deg"] for k in angles):
                self.calibration.clear()
                self.calibration.append((now, dict(angles)))
            if now-self.calibration[0][0] < CONFIG["calibration_seconds"] or len(self.calibration) < 8:
                return self.snapshot("CALIBRATING")
            self.baseline = {k: statistics.median(a[k] for _, a in self.calibration) for k in angles}
            self.calibration.clear()
            self.armed = True
        relative = {k: (angles[k]-self.baseline[k]+180) % 360-180 for k in self.baseline}
        if (abs(relative["yaw"]) > CONFIG["max_yaw_deg"] or abs(relative["roll"]) > CONFIG["max_roll_deg"]
                or not -CONFIG["max_up_deg"] <= relative["pitch"] <= CONFIG["max_down_deg"]):
            self.interrupt()
            return self.snapshot("OUT_OF_RANGE", relative)
        if not self.armed:
            # Reacquisition movement is not a nod. Require one continuous neutral
            # interval before starting a new cycle after any observation break.
            neutral = abs(relative["pitch"]) <= CONFIG["reacquire_neutral_deg"]
            if neutral and self.reacquire_since is None:
                self.reacquire_since = now
            elif not neutral:
                self.reacquire_since = None
            if self.reacquire_since is None or now-self.reacquire_since < CONFIG["reacquire_seconds"]:
                return self.snapshot("REACQUIRING", relative)
            self.armed = True
            self.reacquire_since = None
        while self.nods and now-self.nods[0] > CONFIG["window_seconds"]:
            self.nods.popleft()
        pitch = relative["pitch"]
        if pitch > CONFIG["return_deg"] and self.departed_at is None:
            self.departed_at = now
        if self.departed_at is not None and now-self.departed_at > CONFIG["max_cycle_seconds"]:
            # A long deliberate look down cannot become a nod on recovery.
            self.lowered_at = None
            if pitch > CONFIG["return_deg"]:
                return self.snapshot("LOWERED", relative, eye_closed)
            self.departed_at = None
        if pitch >= CONFIG["down_deg"] and self.lowered_at is None:
            self.lowered_at = now
        if pitch <= CONFIG["return_deg"] and self.departed_at is not None:
            elapsed = now-self.departed_at
            if (self.lowered_at is not None and CONFIG["min_cycle_seconds"] <= elapsed <= CONFIG["max_cycle_seconds"]
                    and now-self.lowered_at >= CONFIG["min_lowered_seconds"]):
                self.nods.append(now)
            self.departed_at = self.lowered_at = None
        state = ("LOWERED" if pitch >= CONFIG["down_deg"] else
                 "MOVING" if self.departed_at is not None else
                 "REPEATED_NODS" if len(self.nods) >= 2 else "NOD_DETECTED" if self.nods else "NEUTRAL")
        return self.snapshot(state, relative, eye_closed)
