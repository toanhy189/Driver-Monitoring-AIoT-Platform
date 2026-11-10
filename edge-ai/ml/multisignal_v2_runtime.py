"""Experimental v2: independent geometry, technical quality, causal smoothing and RF."""
import json
import math
from pathlib import Path
import time

import joblib
import mediapipe as mp
import numpy as np
import sklearn

from config import TASK_PATH
from ml.dataset import sha256_file
from ml.multisignal_v2_features import (CONFIG, DECISION_VERSION, FEATURE_NAMES, FEATURE_VERSION,
    QUALITY_VERSION, V2Window, ProbabilitySmoother, FusionDecision, admitted_values, bundle_version,
    crop_quality, state_and_reason)
from ml.regions import IMAGE_SIZE, REGION_VERSION, extract_regions
from service.alert_policy import POLICY_VERSION
from service.multisignal_eye_guard import build_eye_guard, current_guard_ear, runtime_version
from service.multisignal_calibration import load_profile
from service.head_motion import HeadMotionTracker


class MultisignalModelV2:
    multisignal = True
    kind = "multisignal-v2"

    def __init__(self, bundle, device="cpu", *, calibration=None, profile_id=None,
                 condition=None, camera=0, device_code="vision-01",
                 head_down_risk=False):
        import torch
        from ml.region_net import load_region_net
        bundle = Path(bundle).resolve()
        m = json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
        required = {"format": "driver-multisignal-v2", "feature_version": FEATURE_VERSION,
            "feature_names": list(FEATURE_NAMES), "quality_version": QUALITY_VERSION,
            "decision_version": DECISION_VERSION, "quality_config": CONFIG,
            "region_version": REGION_VERSION, "image_size": IMAGE_SIZE, "policy_version": POLICY_VERSION,
            "landmarker_sha256": sha256_file(TASK_PATH), "mediapipe_version": mp.__version__}
        if any(m.get(k) != v for k, v in required.items()):
            raise ValueError("Incompatible v2 bundle, admission rules or geometry")
        if m.get("model_version") != bundle_version(m.get("files"), m.get("enter_threshold"), m.get("leave_threshold")):
            raise ValueError("Invalid v2 model identity")
        for name in ("regions.pt", "fusion.joblib"):
            if m.get("files", {}).get(name) != sha256_file(bundle/name):
                raise ValueError("V2 model checksum mismatch")
        artifact = joblib.load(bundle/"fusion.joblib")  # own trusted output only
        if (artifact.get("format") != "multisignal-fusion-v2" or artifact.get("feature_version") != FEATURE_VERSION
                or artifact.get("feature_names") != list(FEATURE_NAMES)
                or artifact.get("versions") != {"numpy": np.__version__, "sklearn": sklearn.__version__}
                or artifact.get("threshold") != m.get("enter_threshold")
                or artifact.get("leave_threshold") != m.get("leave_threshold")):
            raise ValueError("Incompatible RF v2 artifact/library versions")
        estimator = artifact["estimator"]
        if list(estimator.classes_) != [0, 1] or estimator.n_features_in_ != len(FEATURE_NAMES):
            raise ValueError("Wrong RF v2 feature shape/classes")
        estimator.set_params(n_jobs=1)  # Avoid creating a thread pool for each webcam observation.
        if device not in {"cpu", "cuda"} or (device == "cuda" and not torch.cuda.is_available()):
            raise ValueError("Inference device unavailable")
        torch.set_num_threads(2)
        self.network, self.device = load_region_net(bundle/"regions.pt", device), device
        self.estimator, self.manifest, self.model_version = estimator, m, m["model_version"]
        self.threshold = artifact["threshold"]
        self.window = V2Window(m["window_seconds"], m["min_history_seconds"], m["max_gap_seconds"])
        self.smoother = ProbabilitySmoother()
        self.decision = FusionDecision(self.threshold, artifact["leave_threshold"])
        self.profile = load_profile(calibration, device_code=device_code, profile_id=profile_id,
            camera=camera, condition=condition) if calibration else None
        self.guard, self.guard_metadata = build_eye_guard(condition, self.profile)
        self.base_model_version = self.model_version
        self.model_version = runtime_version(self.base_model_version, self.guard_metadata)
        self.previous = self.cnn_at = self.last_score = self.last_inference_ms = None
        self.last_diagnostics = None
        self.region_diagnostics = {}; self.cached = {}; self.smoothed = {}; self.failed = False
        self.head_motion = HeadMotionTracker()
        from service.head_down_risk import HeadDownRisk, model_identity as posture_identity
        self.head_down = HeadDownRisk() if head_down_risk else None
        if self.head_down:
            self.model_version=posture_identity(self.model_version)
        self.signals = self._empty_signals("WARMUP")

    def _empty_signals(self, reason):
        return {"schema_version": "eye-mouth-v2", "mar": None, "yawn_probability": None,
            "eye_sleepy_probability": None, "fusion_score": None, "mouth_state": "UNKNOWN",
            "eye_state": "UNKNOWN", "eyes_available": False, "mouth_available": False,
            "experimental": True, "ear_available": False, "eye_confidence": None, "mouth_confidence": None,
            "eye_quality": "NO_FACE" if reason == "NO_FACE" else "NO_CROP",
            "mouth_quality": "NO_FACE" if reason == "NO_FACE" else "NO_CROP",
            "decision_reason": reason, "sample_age_ms": None,
            "eye_closure_state": "DISABLED" if self.guard is None else "UNAVAILABLE",
            "quality_version": QUALITY_VERSION,
            "calibration_id": self.profile.get("_sha256") if self.profile else None,
            "head_motion": self.head_motion.snapshot(),
            "head_down_policy": self.head_down.snapshot() if self.head_down else None}

    def interrupt(self, reason):
        self.window.reset(); self.smoother.reset(); self.decision.update(None)
        self.cached = {}; self.smoothed = {}; self.cnn_at = self.last_score = None
        self.region_diagnostics = {}
        if self.guard: self.guard.reset()
        self.head_motion.interrupt()
        if self.head_down:self.head_down.reset()
        self.signals = self._empty_signals(reason)

    def observe(self, frame, face, now, ear=None, pose=None, pose_status=None, *, head_angles=None):
        self.last_inference_ms = None
        if self.failed:
            return "UNKNOWN"
        if not math.isfinite(now) or (self.previous is not None and now <= self.previous):
            self.interrupt("FRAME_GAP")
            return "UNKNOWN"
        gap = self.previous is not None and now-self.previous > CONFIG["max_gap_seconds"]
        self.previous = now
        if gap or not face or frame is None:
            self.interrupt("FRAME_GAP" if gap else "NO_FACE")
            return "UNKNOWN"
        started = time.perf_counter()
        try:
            if self.profile and list((frame.shape[1], frame.shape[0])) != self.profile["frame_size"]:
                raise ValueError("Camera resolution differs from the calibrated profile")
            regions = extract_regions(frame, face)
            quality = {name: crop_quality(regions[name], regions["eye_sharpness" if name == "eyes" else "mouth_sharpness"])
                       for name in ("eyes", "mouth")}
            # A newly unusable crop invalidates its cached probabilities immediately.
            for region, keys in (("eyes", ("eye_sleepy", "eye_confidence")),
                                 ("mouth", ("mouth_yawn", "mouth_talk", "mouth_confidence"))):
                if not quality[region]["usable"]:
                    for key in keys: self.cached.pop(key, None)
            fresh = self.cnn_at is None or now-self.cnn_at >= CONFIG["cnn_interval_seconds"]-1e-8
            if fresh:
                import torch
                from ml.region_net import image_tensor
                names = [name for name in ("eyes", "mouth") if quality[name]["usable"]]
                self.cached = {}
                if names:
                    images = torch.stack([image_tensor(regions[name]) for name in names]).to(self.device)
                    with torch.inference_mode():
                        e, m = self.network(images)
                        scores = torch.cat((e.softmax(1), m.softmax(1)), dim=1).cpu().numpy()
                    for i, name in enumerate(names):
                        if name == "eyes":
                            self.cached.update(eye_sleepy=float(scores[i, 1]), eye_confidence=float(scores[i, :2].max()))
                        else:
                            self.cached.update(mouth_yawn=float(scores[i, 3]), mouth_talk=float(scores[i, 4]),
                                               mouth_confidence=float(scores[i, 2:].max()))
                self.cnn_at = now
            row = {**self.cached, "ear": ear, "mar": regions["mar"],
                   "yaw": pose.get("yaw") if pose else None, "pitch": pose.get("pitch") if pose else None}
            values = admitted_values(row, quality)
            if fresh:
                values = self.smoother.update(now, values)
                self.smoothed = {key: values[key] for key in ("eye_sleepy", "mouth_yawn", "mouth_talk")}
                self.window.add(now, values)
                snapshot = self.window.snapshot()
                self.last_score = float(self.estimator.predict_proba([snapshot["features"]])[0, 1]) if snapshot else None
                self.decision.update(self.last_score)
            else:
                for key in ("eye_sleepy", "mouth_yawn", "mouth_talk"):
                    if values[key] is not None:
                        values[key] = self.smoothed.get(key)
            eyes, mouth = values["eye_sleepy"] is not None, values["mouth_yawn"] is not None
            # Every guard update consumes a CURRENT geometric observation, never a held EAR.
            guard_ear = current_guard_ear(values["ear"], pose_status)
            closure = self.guard.update(now, guard_ear) if self.guard else False
            motion = self.head_motion.update(now, head_angles,
                neutral_allowed=bool(pose_status and pose_status.get("valid") and
                    (self.head_down is not None or
                     not pose_status.get("calibrating", True) and not pose_status.get("is_deviated"))),
                eye_closed=bool(closure and guard_ear is not None and guard_ear < self.guard.ear_threshold))
            raw, reason = state_and_reason(self.decision.prediction, pose_status, eyes=eyes,
                yawn=values["mouth_yawn"], closure=closure, window_reason=self.window.last_quality_reason)
            posture=self.head_down.update(now,motion) if self.head_down else None
            if posture and posture["risk_candidate"]:
                raw,reason="DROWSY","HEAD_DOWN_RISK"
            guard_state = ("DISABLED" if not self.guard else "UNAVAILABLE" if guard_ear is None else
                "RECOVERING" if self.guard.active and self.guard.open_since is not None else
                "CLOSED_RISK" if self.guard.active else "CLOSING" if self.guard.closed_since is not None else "OPEN")
            ec, mc = values["eye_confidence"], values["mouth_confidence"]
            crop_details = regions.get("crop_details") or {}
            self.signals = {"schema_version": "eye-mouth-v2", "mar": values["mar"],
                "yawn_probability": values["mouth_yawn"], "eye_sleepy_probability": values["eye_sleepy"],
                "fusion_score": self.last_score, "experimental": True, "eyes_available": eyes, "mouth_available": mouth,
                "eye_state": ("SLEEPY" if values["eye_sleepy"] >= .5 else "NORMAL") if eyes and ec >= .6 else "UNKNOWN",
                "mouth_state": ("NORMAL", "YAWN", "TALKING_LAUGHING")[int(np.argmax([
                    1-values["mouth_yawn"]-values["mouth_talk"], values["mouth_yawn"], values["mouth_talk"]]))]
                    if mouth and mc >= .6 else "UNKNOWN",
                "ear_available": values["ear"] is not None, "eye_confidence": ec, "mouth_confidence": mc,
                "eye_quality": quality["eyes"]["reason"], "mouth_quality": quality["mouth"]["reason"],
                "eye_crop_reason": crop_details.get("eyes", {}).get("reason"),
                "mouth_crop_reason": crop_details.get("mouth", {}).get("reason"),
                "decision_reason": reason, "sample_age_ms": round((now-self.cnn_at)*1000, 3),
                "eye_closure_state": guard_state, "quality_version": QUALITY_VERSION,
                "calibration_id": self.profile.get("_sha256") if self.profile else None,
                "head_motion": motion, "head_down_policy":posture}
            self.region_diagnostics = {"eyes_crop_available": regions["eyes"] is not None,
                "mouth_crop_available": regions["mouth"] is not None, "quality": quality,
                "crop_details": regions.get("crop_details"),
                "eye_confidence": ec, "mouth_confidence": mc,
                "eye_probabilities": [1-row["eye_sleepy"], row["eye_sleepy"]] if eyes else None,
                "mouth_probabilities": [1-row["mouth_yawn"]-row["mouth_talk"],row["mouth_yawn"],row["mouth_talk"]] if mouth else None}
            self.last_diagnostics = {"feature_version": FEATURE_VERSION, "signals": self.signals,
                "coverage": self.window.last_coverage, "profile_loaded": self.profile is not None}
            self.last_inference_ms = (time.perf_counter()-started)*1000
            return raw
        except Exception:
            import logging
            logging.getLogger(__name__).exception("V2 inference failed; UNKNOWN until restart")
            self.failed = True; self.interrupt("INFERENCE_FAILED")
            return "UNKNOWN"

    def telemetry_signals(self):
        return dict(self.signals)
