"""Versioned admission and causal features shared by v2 fitting and inference."""
import hashlib
import json
import math

import cv2
import numpy as np

from ml.multisignal_features import MultisignalWindow

FEATURE_VERSION = "eye-mouth-quality-temporal-v2"
QUALITY_VERSION = "region-technical-quality-v1"
DECISION_VERSION = "quality-fusion-hysteresis-v2"
CHANNELS = ("eye_sleepy", "mouth_yawn", "mouth_talk", "ear", "mar", "yaw", "pitch",
            "eye_confidence", "mouth_confidence")
FEATURE_NAMES = tuple(f"{key}_{stat}" for key in CHANNELS for stat in ("mean", "std", "p90", "coverage"))
CONFIG = {"ema_seconds": .4, "max_gap_seconds": .5, "cnn_interval_seconds": .2,
          "min_contrast": 4., "max_extreme_fraction": .65, "min_sharpness": 1.,
          "max_ear": .8, "class_confidence_threshold": .6, "yawn_support_threshold": .6}


def bundle_version(files, enter, leave):
    identity = {"files": files, "feature_version": FEATURE_VERSION, "quality_version": QUALITY_VERSION,
                "decision_version": DECISION_VERSION, "config": CONFIG, "enter": enter, "leave": leave}
    return "eye-mouth-v2-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def crop_quality(crop, sharpness=None):
    """Conservative technical checks, NOT a semantic visibility/glasses detector."""
    if crop is None or crop.size == 0:
        return {"usable": False, "reason": "NO_CROP", "contrast": None, "extreme_fraction": None}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    contrast = float(gray.std())
    extremes = float(np.mean((gray <= 5) | (gray >= 250)))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var()) if sharpness is None else float(sharpness)
    reason = ("BLANK" if not math.isfinite(sharpness) or sharpness < CONFIG["min_sharpness"] else
              "LOW_CONTRAST" if contrast < CONFIG["min_contrast"] else
              "SATURATED" if extremes >= CONFIG["max_extreme_fraction"] else "VALID")
    return {"usable": reason == "VALID", "reason": reason, "contrast": contrast,
            "extreme_fraction": extremes}


def finite(value, low=None, high=None):
    return (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            and (low is None or value >= low) and (high is None or value <= high))


def admitted_values(row, quality, *, mask_eyes=False):
    eyes = quality["eyes"]["usable"] and not mask_eyes
    mouth = quality["mouth"]["usable"]
    # Geometry is independent of CNN certainty and of whether a CNN result exists.
    ear = row.get("ear") if eyes and finite(row.get("ear"), 0, CONFIG["max_ear"]) else None
    return {"ear": ear,
            "eye_sleepy": row.get("eye_sleepy") if eyes and finite(row.get("eye_sleepy"), 0, 1) else None,
            "eye_confidence": row.get("eye_confidence") if eyes and finite(row.get("eye_confidence"), 0, 1) else None,
            "mouth_yawn": row.get("mouth_yawn") if mouth and finite(row.get("mouth_yawn"), 0, 1) else None,
            "mouth_talk": row.get("mouth_talk") if mouth and finite(row.get("mouth_talk"), 0, 1) else None,
            "mouth_confidence": row.get("mouth_confidence") if mouth and finite(row.get("mouth_confidence"), 0, 1) else None,
            "mar": row.get("mar") if mouth and finite(row.get("mar"), 0, 2) else None,
            **{key: row.get(key) if finite(row.get(key)) else None for key in ("yaw", "pitch")}}


class V2Window(MultisignalWindow):
    channels, feature_names = CHANNELS, FEATURE_NAMES


class ProbabilitySmoother:
    def __init__(self):
        self.values, self.times = {}, {}

    def reset(self):
        self.values.clear(); self.times.clear()

    def update(self, now, values):
        result = dict(values)
        for key in ("eye_sleepy", "mouth_yawn", "mouth_talk"):
            value = values.get(key)
            previous = self.times.get(key)
            if value is None:
                self.values.pop(key, None); self.times.pop(key, None)
                continue
            if previous is not None and 0 < now - previous <= CONFIG["max_gap_seconds"]:
                alpha = 1 - math.exp(-(now-previous)/CONFIG["ema_seconds"])
                value = self.values[key] + alpha*(value-self.values[key])
            self.values[key], self.times[key] = value, now
            result[key] = value
        return result


class FusionDecision:
    def __init__(self, enter, leave):
        if not 0 < leave < enter < 1:
            raise ValueError("Expected 0 < leave < enter < 1")
        self.enter, self.leave, self.prediction = enter, leave, None

    def update(self, score):
        if score is None:
            self.prediction = None
        elif not finite(score, 0, 1):
            raise ValueError("Invalid fusion score")
        else:
            self.prediction = int(score >= (self.leave if self.prediction == 1 else self.enter))
        return self.prediction


def state_and_reason(prediction, head, *, eyes, yawn, closure=False, window_reason="WARMUP"):
    if closure:
        return "DROWSY", "EYE_CLOSURE_RISK"
    if prediction == 1 and (eyes or (yawn is not None and yawn >= CONFIG["yawn_support_threshold"])):
        return "DROWSY", "RF_POSITIVE"
    valid = bool(head and head.get("valid") and not head.get("calibrating", True))
    if valid and head.get("is_distracted"):
        return "DISTRACTED", "HEAD_DEVIATION"
    if prediction == 0 and eyes and valid:
        return "ATTENTIVE", "RF_NEGATIVE"
    if prediction is None:
        return "UNKNOWN", "INSUFFICIENT_COVERAGE" if window_reason == "LOW_COVERAGE" else "WARMUP"
    if not valid:
        return "UNKNOWN", "HEAD_CALIBRATING" if head and head.get("valid") else "HEAD_UNAVAILABLE"
    return "UNKNOWN", "INSUFFICIENT_SUPPORT"
