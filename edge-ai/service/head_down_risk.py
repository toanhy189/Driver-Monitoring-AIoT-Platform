"""Explicit posture warning policy requested for the bench demo.

Sustained downward posture maps to DROWSY with a distinct reason. This does not
classify sleep or require eye closure; deliberate looking down can trigger it.
"""
import hashlib
import json
import math

VERSION = "sustained-head-down-v1"
CONFIG = dict(enter_pitch_deg=12., leave_pitch_deg=8., min_seconds=3., recovery_seconds=.5,
              max_yaw_deg=20., max_roll_deg=15., max_pitch_deg=40., max_gap_seconds=.5)


class HeadDownRisk:
    def __init__(self):
        self.reset()

    def reset(self):
        self.previous = self.down_since = self.recovery_since = None
        self.active = False

    def snapshot(self, state="UNAVAILABLE", duration=0.):
        return dict(version=VERSION, state=state, risk_candidate=self.active,
                    observed_down_seconds=round(duration,3), enter_pitch_deg=CONFIG["enter_pitch_deg"],
                    min_seconds=CONFIG["min_seconds"])

    def update(self, now, motion):
        time_ok = isinstance(now,(int,float)) and not isinstance(now,bool) and math.isfinite(now)
        angles_ok = bool(motion and motion.get("available") and motion.get("calibrated")
            and motion.get("state") not in {"UNAVAILABLE","CALIBRATING","OUT_OF_RANGE"}
            and all(isinstance(motion.get(k+"_deg"),(int,float)) and not isinstance(motion[k+"_deg"],bool)
                    and math.isfinite(motion[k+"_deg"]) for k in ("pitch","yaw","roll")))
        gap = time_ok and self.previous is not None and not 0 < now-self.previous <= CONFIG["max_gap_seconds"]
        if not time_ok or not angles_ok or gap:
            self.reset()
            return self.snapshot("CALIBRATING" if motion and motion.get("state")=="CALIBRATING" else "UNAVAILABLE")
        self.previous=now
        pitch=motion["pitch_deg"]
        if (abs(motion["yaw_deg"])>CONFIG["max_yaw_deg"] or abs(motion["roll_deg"])>CONFIG["max_roll_deg"]
                or not -15. <= pitch <= CONFIG["max_pitch_deg"]):
            self.reset()
            return self.snapshot()
        if pitch >= CONFIG["enter_pitch_deg"] or self.active and pitch >= CONFIG["leave_pitch_deg"]:
            self.recovery_since=None
            if self.down_since is None:self.down_since=now
            duration=now-self.down_since
            if duration+1e-8>=CONFIG["min_seconds"]:self.active=True
            return self.snapshot("DOWN_RISK" if self.active else "LOWERED",duration)
        if self.active:
            if self.recovery_since is None:self.recovery_since=now
            if now-self.recovery_since+1e-8<CONFIG["recovery_seconds"]:
                return self.snapshot("RECOVERING",now-self.down_since)
        self.active=False
        self.down_since=self.recovery_since=None
        return self.snapshot("NORMAL")


def model_identity(base):
    from service.head_motion import CONFIG as HEAD_CONFIG, VERSION as HEAD_VERSION
    digest=hashlib.sha256(json.dumps(dict(base=base,version=VERSION,config=CONFIG,
        head_version=HEAD_VERSION,head_config=HEAD_CONFIG),sort_keys=True).encode()).hexdigest()[:16]
    return "eye-mouth-v2-posture-"+digest
