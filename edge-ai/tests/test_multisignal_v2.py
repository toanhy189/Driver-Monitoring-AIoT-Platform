from pathlib import Path
import json
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.multisignal_v2_features import (V2Window, ProbabilitySmoother, FusionDecision,
    admitted_values, crop_quality, state_and_reason)
from ml.multisignal_v2_runtime import MultisignalModelV2
from service.eye_closure_guard import EyeClosureGuard
from service.alert_policy import AlertPolicy
from service.multisignal_calibration import analyze, load_profile
from service.multisignal_eye_guard import build_eye_guard, runtime_version
from service.head_motion import HeadMotionTracker

FRONT = {"valid": True, "calibrating": False, "is_deviated": False, "is_distracted": False}


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.image = np.random.default_rng(11).integers(25, 225, (96, 96, 3), dtype=np.uint8)
        self.quality = {k: crop_quality(self.image) for k in ("eyes", "mouth")}

    def model(self, positive=False, guard=False):
        if not all(importlib.util.find_spec(name) for name in ("torch", "torchvision")):
            self.skipTest("Optional multisignal neural dependencies are not installed")
        import torch
        model = MultisignalModelV2.__new__(MultisignalModelV2)
        model.network = lambda images: (torch.tensor([[0., .04]]).repeat(len(images), 1),
                                        torch.tensor([[.1, 0., .05]]).repeat(len(images), 1))
        model.device = "cpu"
        model.estimator = type("Estimator", (), {"predict_proba": lambda _, rows:
            np.tile([[.05, .95] if positive else [.95, .05]], (len(rows), 1))})()
        model.threshold = .6; model.model_version = "test-v2"
        model.window = V2Window(); model.smoother = ProbabilitySmoother(); model.decision = FusionDecision(.6, .5)
        model.profile = {"frame_size": [96, 96]} if guard else None
        model.guard = EyeClosureGuard(.2) if guard else None
        model.previous = model.cnn_at = model.last_score = model.last_inference_ms = None
        model.last_diagnostics = None; model.region_diagnostics = {}; model.cached = {}; model.smoothed = {}; model.failed = False
        model.head_motion = HeadMotionTracker()
        model.head_down = None
        model.signals = model._empty_signals("WARMUP")
        return model

    def regions(self):
        return {"eyes": self.image, "mouth": self.image, "eye_sharpness": 200., "mouth_sharpness": 200., "mar": .1}

    def observe(self, model, now, ear=.3):
        with patch("ml.multisignal_v2_runtime.extract_regions", return_value=self.regions()):
            return model.observe(self.image, [object()], now, ear, {"yaw": 0., "pitch": .1}, FRONT)

    def test_default_guard_is_only_for_explicit_no_glasses_and_has_its_own_identity(self):
        for condition in (None, "glasses"):
            guard, metadata = build_eye_guard(condition)
            self.assertIsNone(guard)
            self.assertEqual(runtime_version("base-v2", metadata), "base-v2")
        guard, metadata = build_eye_guard("no-glasses")
        self.assertEqual(guard.ear_threshold, .2)
        self.assertEqual(metadata["source"], "NO_GLASSES_DEFAULT")
        self.assertFalse(metadata["calibrated"])
        version = runtime_version("base-v2", metadata)
        self.assertNotEqual(version, "base-v2")
        self.assertEqual(version, runtime_version("base-v2", metadata))
        self.assertNotEqual(version, runtime_version("base-v2", {**metadata, "ear_threshold": .21}))
        with self.assertRaises(ValueError): build_eye_guard("noglasses")
        profile = {"candidate_threshold": .16, "_sha256": "a"*64}
        calibrated, info = build_eye_guard("no-glasses", profile)
        self.assertEqual(calibrated.ear_threshold, .16)
        self.assertEqual(info["source"], "CALIBRATED_PROFILE")
        self.assertNotEqual(version, runtime_version("base-v2", info))

    def test_head_observation_does_not_replace_rf_or_create_drowsy_from_nods(self):
        model = self.model()
        def observe(now, pitch):
            with patch("ml.multisignal_v2_runtime.extract_regions", return_value=self.regions()):
                return model.observe(self.image, [object()], now, .3, {"yaw": 0., "pitch": .1}, FRONT,
                    head_angles=dict(pitch=pitch, yaw=0., roll=0.))
        for i in range(41):
            observe(i*.1, 0.)
        for start in (4.1, 5.5):
            for i in range(12):
                raw = observe(round(start+i*.1, 4), 17. if 2 <= i <= 8 else 0.)
                self.assertEqual(raw, "ATTENTIVE")
        motion = model.telemetry_signals()["head_motion"]
        self.assertTrue(motion["repeated_nods"])
        self.assertEqual(motion["mode"], "OBSERVE_ONLY")
        self.assertFalse(motion["eye_closure_supported"])
        # Missing 3D observations do not erase existing valid eye/RF evidence.
        self.assertEqual(self.observe(model, 6.65), "ATTENTIVE")
        self.assertEqual(model.telemetry_signals()["head_motion"]["state"], "UNAVAILABLE")
        self.assertEqual(model.telemetry_signals()["head_motion"]["nod_count"], 0)


    def test_requested_posture_policy_maps_held_down_to_drowsy_and_existing_alert_levels(self):
        from service.head_down_risk import HeadDownRisk
        model=self.model()
        model.head_down=HeadDownRisk()
        policy=AlertPolicy("posture-bench","posture-test")
        levels=[]
        for i in range(281):
            now=i*.1
            pitch=0. if now<4. or now>=24. else 15.
            head={**FRONT,"is_deviated":pitch>0,"is_distracted":pitch>0}
            with patch("ml.multisignal_v2_runtime.extract_regions",return_value=self.regions()):
                raw=model.observe(self.image,[object()],now,.34,{"yaw":0.,"pitch":.1},head,
                    head_angles=dict(pitch=pitch,yaw=0.,roll=0.))
            events=policy.update(raw,now=now)
            levels.extend(e["level"] for e in events if e["event_type"]=="DROWSY_THRESHOLD_REACHED")
            if 7.1<=now<24.:
                self.assertEqual(raw,"DROWSY")
                self.assertEqual(model.telemetry_signals()["decision_reason"],"HEAD_DOWN_RISK")
                self.assertEqual(model.decision.prediction,0)
        self.assertEqual(levels[:3],[1,2,3])
        self.assertEqual(policy.state,"ATTENTIVE")
        self.assertEqual(model.observe(None,None,28.1),"UNKNOWN")
        self.assertFalse(model.telemetry_signals()["head_down_policy"]["risk_candidate"])

    def test_restored_no_glasses_guard_overrides_negative_rf_and_confident_normal_cnn(self):
        import torch
        model = self.model()
        model.guard, model.guard_metadata = build_eye_guard("no-glasses")
        model.network = lambda images: (torch.tensor([[4., 0.]]).repeat(len(images), 1),
                                        torch.tensor([[4., 0., 0.]]).repeat(len(images), 1))
        policy = AlertPolicy("private-regression", model.model_version)
        warnings = []
        for i in range(106):
            now = i*.2
            ear = .3 if now < 3. or now >= 17. else .036
            raw = self.observe(model, now, ear)
            warnings += [e["level"] for e in policy.update(raw, now=now)
                         if e["event_type"] == "DROWSY_THRESHOLD_REACHED" and not e["repeat"]]
            if 4. <= now < 17.:
                self.assertEqual(raw, "DROWSY")
                self.assertEqual(model.telemetry_signals()["decision_reason"], "EYE_CLOSURE_RISK")
                self.assertEqual(model.telemetry_signals()["eye_state"], "NORMAL")
                self.assertEqual(model.decision.prediction, 0)
        self.assertEqual(warnings, [1, 2, 3])
        self.assertEqual(raw, "ATTENTIVE")
        self.assertEqual(policy.state, "ATTENTIVE")
        self.assertFalse(model.guard.active)

    def test_restored_guard_ignores_short_blinks_and_does_not_gate_normal_on_binary_cnn(self):
        model = self.model()
        model.guard, model.guard_metadata = build_eye_guard("no-glasses")
        for i in range(41):
            now = i*.2
            raw = self.observe(model, now, .08 if 3 <= now < 3.4 or 5 <= now < 5.4 else .3)
            self.assertNotEqual(raw, "DROWSY")
            if now >= 2.: self.assertEqual(raw, "ATTENTIVE")
        self.assertFalse(model.guard.active)

    def test_restored_guard_requires_current_valid_eye_image_and_frontal_head(self):
        model = self.model()
        model.guard, model.guard_metadata = build_eye_guard("no-glasses")
        for i in range(16): self.observe(model, i*.2, .08)
        self.assertTrue(model.guard.active)
        with patch("ml.multisignal_v2_runtime.extract_regions", return_value={**self.regions(), "eyes": None}):
            self.assertEqual(model.observe(self.image, [object()], 3.05, .036, {}, FRONT), "UNKNOWN")
        self.assertFalse(model.guard.active)
        for i in range(16, 23): self.observe(model, i*.2, .08)
        self.assertTrue(model.guard.active)
        with patch("ml.multisignal_v2_runtime.extract_regions", return_value=self.regions()):
            raw = model.observe(self.image, [object()], 4.45, .036, {},
                                {**FRONT, "is_deviated": True, "is_distracted": True})
        self.assertEqual(raw, "DISTRACTED")
        self.assertFalse(model.guard.active)

    def test_class_uncertainty_keeps_soft_probability_and_independent_ear(self):
        values = admitted_values({"eye_sleepy": .51, "eye_confidence": .51, "ear": .31}, self.quality)
        self.assertEqual(values["eye_sleepy"], .51)
        self.assertEqual(values["ear"], .31)
        values = admitted_values({"ear": .31}, self.quality)
        self.assertIsNone(values["eye_sleepy"])
        self.assertEqual(values["ear"], .31)

    def test_invalid_images_are_not_made_valid_by_high_confidence(self):
        quality = {"eyes": crop_quality(np.zeros_like(self.image)), "mouth": self.quality["mouth"]}
        values = admitted_values({"eye_sleepy": .99, "eye_confidence": .99, "ear": .1}, quality)
        self.assertIsNone(values["ear"]); self.assertIsNone(values["eye_sleepy"])
        saturated = self.image.copy(); saturated[:85] = 255
        self.assertEqual(crop_quality(saturated)["reason"], "SATURATED")

    def test_smoothing_is_causal_and_missing_channels_clear_immediately(self):
        smoother = ProbabilitySmoother()
        self.assertEqual(smoother.update(0, {"eye_sleepy": .2})["eye_sleepy"], .2)
        self.assertLess(smoother.update(.2, {"eye_sleepy": .8})["eye_sleepy"], .8)
        self.assertIsNone(smoother.update(.3, {"eye_sleepy": None})["eye_sleepy"])
        self.assertEqual(smoother.update(.4, {"eye_sleepy": .9})["eye_sleepy"], .9)
        self.assertEqual(smoother.update(1.4, {"eye_sleepy": .1})["eye_sleepy"], .1)

    def test_hysteresis_does_not_hold_a_decision_across_missing_evidence(self):
        decision = FusionDecision(.7, .6)
        self.assertEqual([decision.update(x) for x in (.69, .71, .65, None, .65, .71, .59)], [0, 1, 1, None, 0, 1, 0])

    def test_missing_mouth_negative_never_establishes_attentive(self):
        self.assertEqual(state_and_reason(0, FRONT, eyes=False, yawn=.01)[0], "UNKNOWN")
        self.assertEqual(state_and_reason(None, {**FRONT, "is_distracted": True}, eyes=False, yawn=None)[0], "DISTRACTED")

    def test_runtime_keeps_ambiguous_eyes_without_pretending_class_is_certain(self):
        model = self.model()
        for i in range(16): raw = self.observe(model, i*.2)
        self.assertEqual(raw, "ATTENTIVE")
        signals = model.telemetry_signals()
        self.assertTrue(signals["eyes_available"]); self.assertTrue(signals["ear_available"])
        self.assertLess(signals["eye_confidence"], .6)
        self.assertEqual(signals["eye_state"], "UNKNOWN")
        self.assertEqual(signals["decision_reason"], "RF_NEGATIVE")
        # Normal CNN cadence cannot oscillate between smoothed and raw probabilities.
        old = signals["eye_sleepy_probability"]
        self.observe(model, 3.05)
        self.assertEqual(model.telemetry_signals()["eye_sleepy_probability"], old)

    def test_loss_and_gaps_clear_guard_window_and_positive_score(self):
        model = self.model(positive=True, guard=True)
        for i in range(16): self.observe(model, i*.2, .1)
        self.assertEqual(model.telemetry_signals()["decision_reason"], "EYE_CLOSURE_RISK")
        self.assertEqual(model.observe(None, None, 3.05), "UNKNOWN")
        self.assertFalse(model.guard.active); self.assertIsNone(model.last_score)
        self.assertEqual(len(model.window.samples), 0)
        self.assertEqual(self.observe(model, 3.1, .1), "UNKNOWN")
        self.assertEqual(self.observe(model, 4., .1), "UNKNOWN")
        self.assertEqual(model.telemetry_signals()["decision_reason"], "FRAME_GAP")

    def test_current_bad_crop_invalidates_cnn_cache_before_next_inference(self):
        model = self.model(positive=True)
        for i in range(16): self.observe(model, i*.2)
        bad = {**self.regions(), "eyes": None}
        with patch("ml.multisignal_v2_runtime.extract_regions", return_value=bad):
            raw = model.observe(self.image, [object()], 3.05, .1, {}, FRONT)
        self.assertEqual(raw, "UNKNOWN")
        self.assertFalse(model.telemetry_signals()["ear_available"])
        self.assertFalse(model.telemetry_signals()["eyes_available"])

    def test_closure_requires_continuity_and_clears_after_open_recovery(self):
        model = self.model(guard=True)
        for i in range(26): raw = self.observe(model, i*.2, .3 if i < 10 else .1)
        self.assertEqual(raw, "DROWSY")
        for i in range(26, 33): raw = self.observe(model, i*.2, .3)
        self.assertEqual(raw, "ATTENTIVE")
        self.assertEqual(model.telemetry_signals()["eye_closure_state"], "OPEN")

    def test_v2_policy_keeps_three_six_ten_seconds_and_never_counts_missing_time(self):
        model = self.model(positive=True)
        policy = AlertPolicy("test-camera", model.model_version)
        warnings = []
        for i in range(70):
            now = i*.2
            raw = self.observe(model, now)
            warnings += [(now, e["level"]) for e in policy.update(raw, now=now)
                         if e["event_type"] == "DROWSY_THRESHOLD_REACHED"]
        self.assertEqual([level for _, level in warnings], [1, 2, 3])
        self.assertAlmostEqual(warnings[1][0]-warnings[0][0], 3.)
        self.assertAlmostEqual(warnings[2][0]-warnings[0][0], 7.)
        model.observe(None, None, 14.)
        policy.update("UNKNOWN", valid=False, now=14.)
        self.assertIsNone(policy.risk_since)
        events = policy.update(self.observe(model, 15.), now=15.)
        self.assertFalse(any(e["event_type"].endswith("THRESHOLD_REACHED") for e in events))

    def test_profile_binds_operator_camera_condition_resolution_and_rejects_bad_capture(self):
        phase = lambda value, duration=8: [{"elapsed_s": i*.1, "ear": value, "yaw": 0., "pitch": .1} for i in range(int(duration*10)+1)]
        phases = {"open_fit": phase(.32), "closed_fit": phase(.14),
                  "open_validation": phase(.31, 30), "closed_validation": phase(.15)}
        report = analyze(phases, "vision-test", "glasses", capture_completed=True,
                         profile_id="operator-a-camera-a", camera=0, frame_size=(640, 480))
        self.assertEqual(report["status"], "READY_FOR_TRIAL")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"profile.json"; path.write_text(json.dumps(report))
            kwargs = {"device_code": "vision-test", "profile_id": "operator-a-camera-a", "camera": 0, "condition": "glasses"}
            self.assertGreater(load_profile(path, **kwargs)["candidate_threshold"], .14)
            for change in ({"profile_id": "other"}, {"condition": "no-glasses"}, {"camera": 1}):
                with self.assertRaises(ValueError): load_profile(path, **{**kwargs, **change})
            # A calibration-only pass cannot overrule a later reviewed failure.
            import hashlib
            review = {"format": "eye-guard-trial-review-v1", "status": "FAILED",
                      "calibration_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            review_path = path.with_name("fresh-trial-review.json")
            review_path.write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError, "failed a reviewed fresh trial"):
                load_profile(path, **kwargs)
            review["calibration_sha256"] = "0"*64
            review_path.write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError, "mismatched"):
                load_profile(path, **kwargs)
        bad = analyze(phases, "vision-test", "glasses", capture_completed=False,
                      profile_id="operator-a", camera=0, frame_size=(640, 480))
        self.assertEqual(bad["status"], "REJECTED")

    def test_calibration_accepts_short_blinks_but_rejects_sustained_false_closure_and_overlap(self):
        phase = lambda value, duration=8: [{"elapsed_s": i*.1, "ear": value, "yaw": 0., "pitch": .1} for i in range(int(duration*10)+1)]
        opened = phase(.32)
        for row in opened:
            if 1 <= row["elapsed_s"] < 1.3 or 3 <= row["elapsed_s"] < 3.3: row["ear"] = .15
        phases = {"open_fit": opened, "closed_fit": phase(.16),
                  "open_validation": phase(.32, 30), "closed_validation": phase(.16)}
        make = lambda p: analyze(p, "vision-test", "glasses", capture_completed=True,
                                 profile_id="operator", camera=0, frame_size=(640, 480))
        self.assertEqual(make(phases)["status"], "READY_FOR_TRIAL")
        long_blink = phase(.32, 30)
        for row in long_blink:
            if 1 <= row["elapsed_s"] < 2.4: row["ear"] = .15
        self.assertEqual(make({**phases, "open_validation": long_blink})["status"], "REJECTED")
        self.assertEqual(make({**phases, "closed_fit": phase(.31)})["status"], "REJECTED")

    def test_head_reference_comes_from_guided_profile_not_camera_idle(self):
        from service.multisignal_calibration import head_tracker_for_profile
        tracker = head_tracker_for_profile({"head_baseline": {"yaw": .02, "pitch": .19}})
        self.assertFalse(tracker.calibrating)
        self.assertAlmostEqual(tracker.update({"yaw": .33, "pitch": .19})["yaw_diff"], .31)
        tracker.interrupt()
        self.assertAlmostEqual(tracker.yaw_baseline, .02)

    def test_calibration_midpoint_tolerates_closed_jitter_and_never_fits_on_validation(self):
        phase = lambda value, duration=8: [{"elapsed_s": i*.1, "ear": value, "yaw": .02, "pitch": .19}
                                           for i in range(int(duration*10)+1)]
        repeated_closed = phase(.205)
        for row in repeated_closed:
            if int(row["elapsed_s"]*10) % 13 < 3: row["ear"] = .23
        phases = {"open_fit": phase(.30), "closed_fit": phase(.20),
                  "open_validation": phase(.30, 30), "closed_validation": repeated_closed}
        make = lambda data: analyze(data, "v", "glasses", capture_completed=True,
                                   profile_id="operator", camera=0, frame_size=(640, 480))
        report = make(phases)
        self.assertEqual(report["format"], "eye-guard-calibration-v5")
        self.assertEqual(report["status"], "READY_FOR_TRIAL")
        self.assertAlmostEqual(report["candidate_threshold"], .25)
        self.assertEqual(report["temporal_checks"]["closed_validation"]["measured_closed_fraction"], 1.)
        changed = make({**phases, "open_validation": phase(.38, 30), "closed_validation": phase(.19)})
        self.assertEqual(changed["candidate_threshold"], report["candidate_threshold"])
        missed = make({**phases, "closed_validation": phase(.26)})
        self.assertEqual(missed["status"], "REJECTED")
        self.assertEqual(missed["candidate_threshold"], report["candidate_threshold"])
        # An old report cannot be relabeled by its READY status alone.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"report.json"
            path.write_text(json.dumps({**report, "format": "eye-guard-calibration-v4",
                                        "fit_method": "closed-quantile-temporal-validation-v1"}))
            with self.assertRaisesRegex(ValueError, "old or mismatched"):
                load_profile(path, device_code="v", profile_id="operator", camera=0, condition="glasses")

    def test_outside_frame_mouth_is_missing_even_while_eye_geometry_is_valid(self):
        model = self.model()
        regions = {**self.regions(), "mouth": None,
                   "crop_details": {"eyes": {"reason": "VALID"}, "mouth": {"reason": "OUTSIDE_FRAME"}}}
        with patch("ml.multisignal_v2_runtime.extract_regions", return_value=regions):
            for i in range(16):
                model.observe(self.image, [object()], i*.2, .3, {"yaw": 0., "pitch": .1}, FRONT)
        signals = model.telemetry_signals()
        self.assertEqual(signals["mouth_crop_reason"], "OUTSIDE_FRAME")
        self.assertFalse(signals["mouth_available"])
        self.assertIsNone(signals["yawn_probability"])
        self.assertIsNone(signals["mar"])
        self.assertTrue(signals["ear_available"])


if __name__ == "__main__": unittest.main()
