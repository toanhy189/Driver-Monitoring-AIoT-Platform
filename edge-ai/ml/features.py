"""One timestamp-based feature implementation for recorded video and live AI.

Missing frames never mean open eyes. Intervals need two valid observations;
long gaps break eye closures and contribute no observed time.
"""

from collections import deque
from dataclasses import asdict, dataclass
import math

import numpy as np

LEGACY_FEATURE_VERSION = "ear-pose-pixel-blink-v2"
FEATURE_VERSION = "ear-pose-pixel-blink-v3-gap-history"
FEATURE_NAMES = ("ear_mean", "ear_std", "ear_p10", "perclos", "longest_closed_s",
                 "yaw_mean", "yaw_std", "yaw_range", "pitch_mean", "pitch_std",
                 "pitch_range", "ear_p90", "ear_relative_mean", "ear_relative_std",
                 "closed_episodes_per_min", "closed_duration_mean_s", "closed_duration_std_s",
                 "ear_closing_speed_p90", "ear_opening_speed_p90")

FEATURE_GROUPS = {
    "core": FEATURE_NAMES[:11],
    "eyes": tuple(k for k in FEATURE_NAMES if not k.startswith(("yaw_", "pitch_"))),
    "full": FEATURE_NAMES,
}


@dataclass(frozen=True)
class FeatureConfig:
    window_seconds: float = 10.0
    stride_seconds: float = 2.0
    sample_hz: float = 10.0
    ear_threshold: float = 0.20
    max_gap_seconds: float = 0.5
    min_coverage: float = 0.8
    # Retained for legacy v2 windows and baseline replay. V3 keeps bounded
    # history; missing intervals still interrupt closures and add no coverage.
    face_loss_reset_seconds: float = 1.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError("Feature configuration must contain finite positive values")
        if self.min_coverage > 1 or self.stride_seconds > self.window_seconds:
            raise ValueError("Invalid coverage or stride")
        if 1 / self.sample_hz > self.max_gap_seconds:
            raise ValueError("Sampling interval exceeds the maximum observation gap")


@dataclass(frozen=True)
class Observation:
    timestamp: float
    ear: float | None
    yaw: float | None
    pitch: float | None

    @property
    def valid(self):
        return all(v is not None and math.isfinite(v) for v in (self.ear, self.yaw, self.pitch))


class FeatureWindow:
    reset_history_on_face_loss = False

    def __init__(self, config=None):
        self.config = config or FeatureConfig()
        self.samples = deque()
        self.last_timestamp = None
        self.last_sample = None
        self.last_valid = None
        self.last_quality_reason = "no_history"

    def add(self, timestamp, ear=None, pose=None):
        timestamp = float(timestamp)
        if not math.isfinite(timestamp) or (self.last_timestamp is not None
                                           and timestamp <= self.last_timestamp):
            raise ValueError("Observation timestamps must be finite and strictly increasing")
        self.last_timestamp = timestamp
        pose = pose or {}
        observation = Observation(timestamp, ear, pose.get("yaw"), pose.get("pitch"))
        # Invalid observations are always retained to interrupt continuity.
        if (observation.valid and self.last_sample is not None
                and timestamp - self.last_sample < 1 / self.config.sample_hz - 1e-8):
            return False
        self.last_sample = timestamp
        if (self.reset_history_on_face_loss and self.last_valid is not None
                and timestamp - self.last_valid >= self.config.face_loss_reset_seconds):
            self.samples.clear()
        if observation.valid:
            self.last_valid = timestamp
        self.samples.append(observation)
        start = timestamp - self.config.window_seconds
        while len(self.samples) > 1 and self.samples[1].timestamp <= start:
            self.samples.popleft()
        return True

    def snapshot(self, end=None):
        if not self.samples:
            self.last_quality_reason = "no_history"
            return None
        end = self.samples[-1].timestamp if end is None else float(end)
        start = end - self.config.window_seconds
        if self.samples[0].timestamp > start + 1e-7:
            self.last_quality_reason = "insufficient_continuous_history"
            return None
        current = self.samples[-1]
        if not current.valid:
            self.last_quality_reason = "invalid_current_observation"
            return None
        if end - current.timestamp > self.config.max_gap_seconds:
            self.last_quality_reason = "stale_current_observation"
            return None
        values, weights = [], []
        durations, closing_speeds, opening_speeds = [], [], []
        complete_start = False
        previous_closed = None
        run = longest = closed = observed = 0.0
        for previous, following in zip(self.samples, list(self.samples)[1:]):
            duration = min(end, following.timestamp) - max(start, previous.timestamp)
            if duration <= 0:
                continue
            if (not previous.valid or not following.valid
                    or following.timestamp - previous.timestamp > self.config.max_gap_seconds):
                run = 0.0
                previous_closed, complete_start = None, False
                continue
            observed += duration
            values.append((previous.ear, previous.yaw, previous.pitch))
            weights.append(duration)
            is_closed = previous.ear < self.config.ear_threshold
            speed = (following.ear - previous.ear) / (following.timestamp - previous.timestamp)
            if speed < 0:
                closing_speeds.append(-speed)
            elif speed > 0:
                opening_speeds.append(speed)
            if is_closed:
                if previous_closed is not True:
                    complete_start = previous_closed is False
                closed += duration
                run += duration
                longest = max(longest, run)
            else:
                if previous_closed and complete_start:
                    durations.append(run)
                run = 0.0
            previous_closed = is_closed
        coverage = observed / self.config.window_seconds
        if not values or coverage + 1e-8 < self.config.min_coverage:
            self.last_quality_reason = "insufficient_valid_coverage"
            return None
        values, weights = np.asarray(values), np.asarray(weights)
        mean = np.average(values, axis=0, weights=weights)
        std = np.sqrt(np.average((values - mean) ** 2, axis=0, weights=weights))
        order = np.argsort(values[:, 0])
        p10_index = np.searchsorted(np.cumsum(weights[order]), 0.1 * observed)
        p10 = values[order[min(p10_index, len(order) - 1)], 0]
        p90_index = np.searchsorted(np.cumsum(weights[order]), 0.9 * observed)
        p90 = float(values[order[min(p90_index, len(order) - 1)], 0])
        # Window-local reference is causal, not an assertion of fully open eyes.
        reference = max(p90, 1e-8)
        result = (mean[0], std[0], p10, closed / observed, longest,
                  mean[1], std[1], np.ptp(values[:, 1]), mean[2], std[2],
                  np.ptp(values[:, 2]), p90, mean[0] / reference, std[0] / reference,
                  len(durations) * 60 / observed,
                  float(np.mean(durations)) if durations else 0.0,
                  float(np.std(durations)) if durations else 0.0,
                  float(np.percentile(closing_speeds, 90)) if closing_speeds else 0.0,
                  float(np.percentile(opening_speeds, 90)) if opening_speeds else 0.0)
        self.last_quality_reason = "accepted_quality"
        return {"features": dict(zip(FEATURE_NAMES, map(float, result))),
                "coverage": float(coverage), "start_s": float(start), "end_s": float(end)}


class LegacyFeatureWindow(FeatureWindow):
    """Exact v2 history-reset behavior for already trained artifacts."""

    reset_history_on_face_loss = True


def window_for_version(version, config):
    if version == FEATURE_VERSION:
        return FeatureWindow(config)
    if version == LEGACY_FEATURE_VERSION:
        return LegacyFeatureWindow(config)
    raise ValueError("Unsupported feature version")
