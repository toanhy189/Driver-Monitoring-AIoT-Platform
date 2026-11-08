"""Opt-in inference. Load only your own trusted joblib artifacts."""

import logging
import math
import time
from pathlib import Path

import numpy as np

from ml.features import (FEATURE_NAMES, FEATURE_GROUPS, FEATURE_VERSION, LEGACY_FEATURE_VERSION,
                         FeatureConfig, window_for_version)

logger = logging.getLogger(__name__)


def fuse_state(binary_prediction, pose_status):
    """A non-drowsy prediction still needs the existing head-pose rules."""
    if binary_prediction is None:
        return "UNKNOWN"
    if isinstance(binary_prediction, str):
        if binary_prediction == "DROWSY":
            return "DROWSY"
        if binary_prediction in {"ATTENTIVE", "DISTRACTED"} and pose_status and pose_status.get("valid") and not pose_status.get("calibrating", True):
            return binary_prediction
        return "UNKNOWN"
    if binary_prediction == 1:
        return "DROWSY"
    if pose_status and pose_status.get("is_distracted", False):
        return "DISTRACTED"
    if pose_status and pose_status.get("valid", False) and not pose_status.get("calibrating", True):
        return "ATTENTIVE"
    return "UNKNOWN"


class DrowsinessModel:
    def __init__(self, path):
        import joblib
        import mediapipe as mp
        import sklearn
        from config import TASK_PATH
        from ml.dataset import sha256_file
        from ml.train import ARTIFACT_FORMAT

        artifact = joblib.load(Path(path))
        self.multiclass = artifact.get("format") == "driver-state-v1"
        if (artifact["format"] not in {ARTIFACT_FORMAT, "driver-state-v1"}
                or artifact["feature_version"] not in {FEATURE_VERSION, LEGACY_FEATURE_VERSION}
                or artifact["feature_names"] not in [list(v) for v in FEATURE_GROUPS.values()]
                or artifact["label_mapping"] != ({"ATTENTIVE": 0, "DISTRACTED": 1, "DROWSY": 2}
                    if self.multiclass else {"ALERT": 0, "DROWSY": 1})
                or artifact["kind"] not in {"rf", "svm"}):
            raise ValueError("Incompatible model schema/features/labels")
        if (artifact["versions"]["sklearn"] != sklearn.__version__
                or artifact["versions"]["numpy"] != np.__version__
                or artifact["mediapipe_version"] != mp.__version__
                or artifact["landmarker_sha256"] != sha256_file(TASK_PATH)):
            raise ValueError("Training/runtime library or landmark model mismatch; re-train in this environment")
        self.feature_names = artifact["feature_names"]
        self.estimator = artifact["estimator"]
        if (list(self.estimator.classes_) != ([0, 1, 2] if self.multiclass else [0, 1])
                or self.estimator.n_features_in_ != len(self.feature_names)):
            raise ValueError("Incompatible estimator input/output")
        self.threshold = float(artifact["threshold"])
        if not math.isfinite(self.threshold):
            raise ValueError("Invalid model threshold")
        self.kind = artifact["kind"]
        self.model_version = artifact["model_version"]
        if not isinstance(self.model_version, str) or not 1 <= len(self.model_version) <= 80:
            raise ValueError("Invalid model version")
        self.config = FeatureConfig(**artifact["feature_config"])
        self.feature_version = artifact["feature_version"]
        self.window = window_for_version(self.feature_version, self.config)
        self.next_prediction = None
        self.prediction = None
        self.last_seen = None
        self.failed = False
        self.last_inference_ms = None
        self.last_score = None
        self.last_diagnostics = None

    def update(self, now, ear=None, pose=None):
        self.last_inference_ms = None
        self.last_diagnostics = None
        if self.failed:
            self.last_score = None
            return None
        try:
            accepted = self.window.add(now, ear, pose)
            if not accepted:
                return self.prediction
            current = self.window.samples[-1] if self.window.samples else None
            if current is None or not current.valid:
                self.prediction = None
                self.last_score = None
                self.next_prediction = None
                return None
            if (self.last_seen is not None
                    and now - self.last_seen > self.config.max_gap_seconds):
                self.prediction, self.next_prediction = None, None
            self.last_seen = now
            if self.next_prediction is None or now >= self.next_prediction - 1e-8:
                snapshot = self.window.snapshot(now)
                if snapshot is None:
                    self.prediction = None
                    self.last_score = None
                    return None
                from ml.train import score_model
                values = np.array([[snapshot["features"][k] for k in self.feature_names]])
                started = time.perf_counter()
                score = None
                if self.multiclass:
                    prediction = int(self.estimator.predict(values)[0])
                    self.prediction = {0: "ATTENTIVE", 1: "DISTRACTED", 2: "DROWSY"}[prediction]
                else:
                    score = float(score_model(self.estimator, values, self.kind)[0])
                    if not math.isfinite(score):
                        raise ValueError("Non-finite classifier score")
                    self.prediction = int(score >= self.threshold)
                self.last_inference_ms = (time.perf_counter() - started) * 1000
                self.last_score = score
                self.last_diagnostics = {"model_version": self.model_version,
                    "feature_version": self.feature_version,
                    "score": score, "threshold": self.threshold,
                    "prediction": self.prediction, "coverage": snapshot["coverage"],
                    "start_s": snapshot["start_s"], "end_s": snapshot["end_s"],
                    "window_seconds": self.config.window_seconds, "features": snapshot["features"]}
                self.next_prediction = now + self.config.stride_seconds
            return self.prediction
        except Exception:
            # A failed model must not silently report a previously cached state.
            logger.exception("ML inference failed; reporting UNKNOWN until restart")
            self.failed, self.prediction = True, None
            self.last_score = None
            return None


def load_optional_model(mode, path):
    if mode == "baseline":
        return None
    if mode != "ml":
        raise ValueError("AI_MODEL_MODE must be baseline or ml")
    try:
        model = DrowsinessModel(path)
        logger.info("Loaded ML model %s", model.model_version)
        return model
    except Exception:
        logger.exception("Cannot load ML model; explicitly falling back to baseline")
        return None
