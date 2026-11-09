"""Explicit experimental eye/mouth model. Never silently falls back to another model."""
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
from ml.multisignal_features import FEATURE_NAMES, FEATURE_VERSION, MultisignalWindow, bundle_version
from ml.regions import REGION_VERSION, IMAGE_SIZE, extract_regions
from service.alert_policy import POLICY_VERSION


def fused_state(prediction, pose_status, *, eyes_available=False, mouth_yawn=None, yawn_threshold=.6):
    if prediction == 1:
        if eyes_available or (mouth_yawn is not None and mouth_yawn >= yawn_threshold):
            return "DROWSY"
    pose_valid = bool(pose_status and pose_status.get("valid") and not pose_status.get("calibrating", True))
    if pose_valid and pose_status.get("is_distracted"):
        return "DISTRACTED"
    if prediction == 0 and eyes_available and pose_valid:
        return "ATTENTIVE"
    return "UNKNOWN"


class MultisignalModel:
    multisignal = True
    kind = "multisignal"

    def __init__(self, bundle, device="cpu"):
        import torch
        from ml.region_net import load_region_net
        bundle = Path(bundle).resolve()
        manifest = json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("format") != "driver-multisignal-v1" or manifest.get("region_version") != REGION_VERSION
                or manifest.get("image_size") != IMAGE_SIZE or manifest.get("policy_version") != POLICY_VERSION
                or manifest.get("model_version") != bundle_version(manifest.get("files",{}))
                or manifest.get("feature_version") != FEATURE_VERSION or manifest.get("feature_names") != list(FEATURE_NAMES)
                or manifest.get("landmarker_sha256") != sha256_file(TASK_PATH)
                or manifest.get("mediapipe_version") != mp.__version__):
            raise ValueError("Incompatible multisignal bundle/landmark geometry")
        for name in ("eye_confidence_threshold","mouth_confidence_threshold"):
            if not isinstance(manifest.get(name),(int,float)) or not 0 < manifest[name] < 1:
                raise ValueError("Invalid region confidence threshold")
        for name in ("regions.pt", "fusion.joblib"):
            if manifest.get("files", {}).get(name) != sha256_file(bundle/name):
                raise ValueError("Multisignal model checksum mismatch")
        artifact = joblib.load(bundle/"fusion.joblib")  # own trusted, hash-checked training output only
        if (artifact.get("format") != "multisignal-fusion-v1" or artifact.get("feature_version") != FEATURE_VERSION
                or artifact.get("feature_names") != list(FEATURE_NAMES)
                or artifact.get("versions") != {"numpy":np.__version__,"sklearn":sklearn.__version__}):
            raise ValueError("Incompatible temporal estimator/library versions")
        if device not in {"cpu", "cuda"} or (device == "cuda" and not torch.cuda.is_available()):
            raise ValueError("Requested inference device unavailable")
        torch.set_num_threads(2)
        self.network = load_region_net(bundle/"regions.pt",device)
        self.device, self.manifest, self.estimator = device,manifest,artifact["estimator"]
        self.model_version = manifest["model_version"]
        if not isinstance(self.model_version,str) or not 1 <= len(self.model_version) <= 80:
            raise ValueError("Invalid multisignal model version")
        self.threshold = artifact["threshold"]
        if not math.isfinite(self.threshold) or not 0 < self.threshold < 1:
            raise ValueError("Invalid fusion threshold")
        if list(self.estimator.classes_) != [0,1] or self.estimator.n_features_in_ != len(FEATURE_NAMES):
            raise ValueError("Invalid fusion classes/features")
        self.window = MultisignalWindow(manifest["window_seconds"],manifest["min_history_seconds"],manifest["max_gap_seconds"])
        self.previous = None
        self.last_score = self.last_inference_ms = self.last_diagnostics = None
        self.signals = None
        self.failed = False

    def observe(self, frame, face, now, ear=None, pose=None, pose_status=None):
        self.last_inference_ms = None
        if self.failed:
            self.signals = None
            return "UNKNOWN"
        if self.previous is not None and now <= self.previous:
            self.window.reset()
            self.signals = None
            return "UNKNOWN"
        # Run the CNN at 5 Hz; current face loss immediately invalidates a cached
        # observation. Cached observations never outlive the source gap limit.
        if not face:
            self.window.add(now,{})
            self.previous = now
            self.signals = self._empty_signals()
            self.last_score = None
            return "UNKNOWN"
        if self.signals and now - self.signals.get("_observed", -math.inf) < .2 - 1e-8:
            return fused_state(self.signals.get("_prediction"),pose_status,
                eyes_available=self.signals["eyes_available"],mouth_yawn=self.signals["yawn_probability"])
        started = time.perf_counter()
        try:
            import torch
            from ml.region_net import image_tensor
            regions = extract_regions(frame,face)
            available = [(name,crop) for name in ("eyes","mouth") for crop in [regions[name]] if crop is not None]
            scores = {}
            if available:
                images = torch.stack([image_tensor(crop) for _,crop in available]).to(self.device)
                with torch.inference_mode():
                    eyes,mouth = self.network(images)
                    probabilities=torch.cat((eyes.softmax(1),mouth.softmax(1)),dim=1).cpu().numpy()
                    eyes,mouth=probabilities[:,:2],probabilities[:,2:]
                for index,(name,_) in enumerate(available):
                    scores[name] = eyes[index] if name == "eyes" else mouth[index]
            eyes_available = "eyes" in scores and float(scores["eyes"].max()) >= self.manifest["eye_confidence_threshold"]
            mouth_available = "mouth" in scores and float(scores["mouth"].max()) >= self.manifest["mouth_confidence_threshold"]
            values = {"eye_sleepy":float(scores["eyes"][1]) if eyes_available else None,
                "mouth_yawn":float(scores["mouth"][1]) if mouth_available else None,
                "mouth_talk":float(scores["mouth"][2]) if mouth_available else None,
                "ear":ear if eyes_available else None,"mar":regions["mar"] if mouth_available else None,
                "yaw":pose.get("yaw") if pose else None,"pitch":pose.get("pitch") if pose else None}
            self.window.add(now,values)
            snapshot = self.window.snapshot()
            prediction = None
            self.last_score = None
            if snapshot is not None:
                self.last_score = float(self.estimator.predict_proba([snapshot["features"]])[0,1])
                if not math.isfinite(self.last_score):
                    raise ValueError("Non-finite fusion score")
                prediction = int(self.last_score >= self.threshold)
            self.signals = {"schema_version":"eye-mouth-v1","mar":values["mar"],
                "yawn_probability":values["mouth_yawn"],"eye_sleepy_probability":values["eye_sleepy"],
                "mouth_state":("NORMAL","YAWN","TALKING_LAUGHING")[int(scores["mouth"].argmax())] if mouth_available else "UNKNOWN",
                "eye_state":("NORMAL","SLEEPY")[int(scores["eyes"].argmax())] if eyes_available else "UNKNOWN",
                "eyes_available":eyes_available,"mouth_available":mouth_available,
                "fusion_score":self.last_score,"experimental":True,"_observed":now,"_prediction":prediction}
            self.last_diagnostics = {"model_version":self.model_version,"feature_version":FEATURE_VERSION,
                "score":self.last_score,"threshold":self.threshold,"signals":self.telemetry_signals(),
                "coverage":snapshot["coverage"] if snapshot else None}
            self.previous = now
            self.last_inference_ms = (time.perf_counter()-started)*1000
            return fused_state(prediction,pose_status,eyes_available=eyes_available,mouth_yawn=values["mouth_yawn"])
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Multisignal inference failed; UNKNOWN until restart")
            self.failed = True
            self.window.reset()
            self.signals = None
            self.last_score = None
            return "UNKNOWN"

    def _empty_signals(self):
        return {"schema_version":"eye-mouth-v1","mar":None,"yawn_probability":None,
                "eye_sleepy_probability":None,"mouth_state":"UNKNOWN","eye_state":"UNKNOWN",
                "eyes_available":False,"mouth_available":False,"fusion_score":None,"experimental":True}

    def telemetry_signals(self):
        return {key:value for key,value in (self.signals or self._empty_signals()).items() if not key.startswith("_")}
