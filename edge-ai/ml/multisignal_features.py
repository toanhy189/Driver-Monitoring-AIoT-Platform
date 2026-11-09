"""Causal missing-aware features, shared by offline training and webcam inference."""
from collections import deque
import hashlib
import json
import math

import numpy as np

FEATURE_VERSION = "eye-mouth-probability-temporal-v1"
CHANNELS = ("eye_sleepy", "mouth_yawn", "mouth_talk", "ear", "mar", "yaw", "pitch")
FEATURE_NAMES = tuple(f"{key}_{stat}" for key in CHANNELS for stat in ("mean", "std", "p90", "coverage"))


def bundle_version(files):
    identity=json.dumps({"feature_version":FEATURE_VERSION,"files":files},sort_keys=True).encode()
    return "eye-mouth-fusion-20261110-"+hashlib.sha256(identity).hexdigest()[:12]


class MultisignalWindow:
    def __init__(self, seconds=5., min_history=2., max_gap=.5):
        if not 0 < min_history <= seconds or not 0 < max_gap <= seconds:
            raise ValueError("Invalid temporal window")
        self.seconds, self.min_history, self.max_gap = seconds, min_history, max_gap
        self.samples = deque()

    def reset(self):
        self.samples.clear()

    def add(self, now, signals):
        if not math.isfinite(now) or (self.samples and now <= self.samples[-1][0]):
            self.reset()
            raise ValueError("Expected increasing monotonic observations")
        if self.samples and now - self.samples[-1][0] > self.max_gap:
            self.reset()
        cleaned = {key: float(value) if value is not None and math.isfinite(value) else None
                   for key in CHANNELS for value in [signals.get(key)]}
        self.samples.append((now, cleaned))
        while len(self.samples) > 1 and self.samples[1][0] <= now - self.seconds:
            self.samples.popleft()

    def snapshot(self):
        if len(self.samples) < 2:
            return None
        now = self.samples[-1][0]
        elapsed = now - self.samples[0][0]
        if elapsed + 1e-8 < self.min_history:
            return None
        features = {}
        for key in CHANNELS:
            values, weights = [], []
            for first, second in zip(self.samples, list(self.samples)[1:]):
                duration = second[0] - max(first[0], now - self.seconds)
                if (duration <= 0 or second[0] - first[0] > self.max_gap
                        or first[1][key] is None or second[1][key] is None):
                    continue
                values.append((first[1][key] + second[1][key]) / 2)
                weights.append(duration)
            coverage = sum(weights) / min(elapsed, self.seconds)
            features[f"{key}_coverage"] = min(1., coverage)
            if values:
                mean = float(np.average(values, weights=weights))
                std = float(np.sqrt(np.average((np.asarray(values) - mean) ** 2, weights=weights)))
                order = np.argsort(values)
                cumulative = np.cumsum(np.asarray(weights)[order]) / sum(weights)
                p90 = float(np.asarray(values)[order][min(np.searchsorted(cumulative, .9), len(order)-1)])
            else:
                # Explicit coverage masks distinguish this fill value from a
                # measured zero. Missing data never become open/normal eyes.
                mean = std = p90 = 0.
            features.update({f"{key}_mean": mean, f"{key}_std": std, f"{key}_p90": p90})
        if max(features["eye_sleepy_coverage"], features["mouth_yawn_coverage"]) < .6:
            return None
        return {"start_s": max(self.samples[0][0], now-self.seconds), "end_s": now,
                "features": [features[key] for key in FEATURE_NAMES], "coverage": features}


def window_label(samples, start, end):
    """Time-weighted original drowsiness labels; ambiguous windows are excluded."""
    positive = total = 0.
    for first, second in zip(samples, samples[1:]):
        duration = min(end, second["time_s"]) - max(start, first["time_s"])
        if duration > 0 and second["time_s"] - first["time_s"] <= .5:
            positive += duration * first["drowsiness"]
            total += duration
    if total <= 0:
        return None
    fraction = positive / total
    return 1 if fraction >= .8 else 0 if fraction <= .2 else None
