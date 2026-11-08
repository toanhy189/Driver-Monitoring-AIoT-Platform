"""ML mechanics only: synthetic observations, temporary files, no accuracy claim."""

import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import joblib
import mediapipe as mp
import numpy as np
import pandas as pd
import main as app

from config import TASK_PATH
from mqtt_client import MQTTClient
from service.message import publisher
from face_detection import FaceLandmarkDetector
from ml.baseline import BaselineReplay
from ml.dataset import make_manifest, read_manifest, sha256_file
from ml.extract import extract, extract_video
from ml.features import (FEATURE_NAMES, FEATURE_VERSION, LEGACY_FEATURE_VERSION,
                         FeatureConfig, FeatureWindow, LegacyFeatureWindow)
from ml.runtime import DrowsinessModel, fuse_state, load_optional_model
from ml.plot_report import plot_report
from ml.train import load_features, score_model, split_subjects, train

POSE = {"yaw": 0.1, "pitch": 0.2}


class FeatureTests(unittest.TestCase):
    def test_time_weighting_and_continuous_closure(self):
        window = FeatureWindow(FeatureConfig(sample_hz=4))
        for tick in range(41):
            now = tick / 4
            window.add(now, 0.1 if now < 2.5 else 0.3, POSE)
        result = window.snapshot()
        self.assertAlmostEqual(result["coverage"], 1)
        self.assertAlmostEqual(result["features"]["perclos"], 0.25)
        self.assertAlmostEqual(result["features"]["longest_closed_s"], 2.5)
        self.assertAlmostEqual(result["features"]["ear_mean"], 0.25)
        self.assertAlmostEqual(result["features"]["ear_p10"], 0.1)

    def test_irregular_intervals_use_duration_not_frame_count(self):
        window = FeatureWindow(FeatureConfig(window_seconds=1, stride_seconds=1, sample_hz=10))
        for now, ear in [(0, 0.1), (0.4, 0.3), (0.5, 0.3), (1, 0.3)]:
            window.add(now, ear, POSE)
        self.assertAlmostEqual(window.snapshot()["features"]["perclos"], 0.4)

    def test_missing_data_is_not_open_eyes_and_long_gap_requires_coverage(self):
        window = FeatureWindow(FeatureConfig(sample_hz=4))
        for tick in range(41):
            now = tick / 4
            window.add(now, None if now == 5 else 0.1, None if now == 5 else POSE)
        snapshot = window.snapshot()
        self.assertAlmostEqual(snapshot["coverage"], 0.95)
        self.assertAlmostEqual(snapshot["features"]["perclos"], 1)
        self.assertLess(snapshot["features"]["longest_closed_s"], 10)
        window.add(15, 0.1, POSE)
        self.assertIsNone(window.snapshot())
        for tick in range(1, 41):
            window.add(15 + tick / 4, 0.3, POSE)
        # The time-bounded window has now evicted all pre-gap data.
        self.assertAlmostEqual(window.snapshot()["features"]["perclos"], 0.025)
        self.assertAlmostEqual(window.snapshot()["features"]["longest_closed_s"], 0.25)

    def test_poor_coverage_invalid_values_and_timestamp_reversal_rejected(self):
        window = FeatureWindow()
        for tick in range(101):
            now = tick / 10
            window.add(now, 0.3 if tick % 3 == 0 else None, POSE)
        self.assertIsNone(window.snapshot())
        window.add(10.1, float("nan"), POSE)
        self.assertIsNone(window.snapshot())
        with self.assertRaises(ValueError):
            window.add(10.0, 0.3, POSE)
        with self.assertRaises(ValueError):
            FeatureConfig(sample_hz=1)

    def test_baseline_replay_recovery_and_missing_gap(self):
        baseline = BaselineReplay(FeatureConfig(sample_hz=4))
        for tick in range(45):
            prediction = baseline.update(tick / 4, 0.1)
        self.assertEqual(prediction, 1)
        for tick in range(45, 50):
            prediction = baseline.update(tick / 4, 0.3)
        self.assertEqual(prediction, 0)
        self.assertIsNone(baseline.update(14, None))
        self.assertIsNone(baseline.update(15, 0.3))

    def test_detector_accepts_source_time_without_wall_clock(self):
        detector = FaceLandmarkDetector.__new__(FaceLandmarkDetector)
        detector.timestamp_ms = -1
        detector.landmarker = Mock()
        detector.landmarker.detect_for_video.return_value = SimpleNamespace(face_landmarks=[])
        frame = np.zeros((8, 8, 3), dtype=np.uint8)
        with patch("face_detection.time.monotonic", side_effect=AssertionError("wall clock used")):
            detector.process(frame, timestamp_ms=0)
            detector.process(frame, timestamp_ms=275)
        self.assertEqual([call.args[1] for call in detector.landmarker.detect_for_video.call_args_list], [0, 275])
        with self.assertRaises(ValueError):
            detector.process(frame, timestamp_ms=275)


class DatasetTests(unittest.TestCase):
    def test_manifest_labels_exclude_low_vigilance_and_reject_unknown_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            videos = root / "raw" / "01"
            videos.mkdir(parents=True)
            for name in ("0.mp4", "5.mp4", "10.mp4"):
                (videos / name).write_bytes(name.encode())
            make_manifest(root / "raw", root / "manifest.csv")
            rows = read_manifest(root / "manifest.csv")
            self.assertEqual({r["label"] for r in rows}, {"ALERT", "DROWSY"})
            self.assertEqual(len(rows), 2)
            (videos / "unknown.mp4").write_bytes(b"x")
            with self.assertRaises(ValueError):
                make_manifest(root / "raw", root / "bad.csv")
            with self.assertRaises(ValueError):
                make_manifest(root / "empty", root / "empty.csv")

    def test_extraction_uses_video_time_and_resumes_without_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subject = root / "raw" / "01"
            subject.mkdir(parents=True)
            for label in (0, 10):
                # Different source bytes, synthetic test videos only.
                writer = cv2.VideoWriter(str(subject / f"{label}.mp4"),
                                         cv2.VideoWriter_fourcc(*"mp4v"), 10, (32, 32))
                self.assertTrue(writer.isOpened())
                for i in range(125):
                    writer.write(np.full((32, 32, 3), label + i % 2, dtype=np.uint8))
                writer.release()
            make_manifest(root / "raw", root / "manifest.csv")
            detectors = []

            def fake_detector():
                detector = Mock()
                detector.process.return_value = [["synthetic landmarks"]]
                detectors.append(detector)
                return detector

            config = FeatureConfig()
            with patch("ml.extract.FaceLandmarkDetector", side_effect=fake_detector), \
                    patch("ml.extract.calculate_average_ear", return_value=0.3), \
                    patch("ml.extract.HeadPoseEstimator") as head:
                head.return_value.estimate.return_value = POSE
                output = extract(root / "manifest.csv", root / "features", config)
            self.assertEqual(len(detectors), 2)
            timestamps = [call.kwargs["timestamp_ms"] for call in detectors[0].process.call_args_list]
            self.assertEqual(timestamps[0], 0)
            self.assertGreater(timestamps[-1], 12000)
            self.assertTrue(all(a < b for a, b in zip(timestamps, timestamps[1:])))
            frame = pd.read_csv(output)
            self.assertTrue((frame.coverage > 0.99).all())
            with patch("ml.extract.FaceLandmarkDetector", side_effect=AssertionError("cache not reused")):
                extract(root / "manifest.csv", root / "features", config)
                checksum_before = sha256_file(output)
                extract(root / "manifest.csv", root / "features", config, cache_only=True)
                self.assertEqual(sha256_file(output), checksum_before)
                extract(root / "manifest.csv", root / "features", config, allow_duplicate_pts=True)
                self.assertEqual(sha256_file(output), checksum_before)
            load_features(output)

    def test_duplicate_pts_can_be_skipped_but_backwards_or_excess_duplicates_fail(self):
        class Capture:
            def __init__(self, mode):
                self.index, self.mode = -1, mode

            def isOpened(self):
                return True

            def get(self, property):
                if property == cv2.CAP_PROP_FPS:
                    return 10.0
                if property == cv2.CAP_PROP_FRAME_COUNT:
                    return 1001.0
                if property == cv2.CAP_PROP_POS_MSEC:
                    if self.index == 500:
                        return 49800 if self.mode == "backwards" else 49900
                    if self.mode == "excess" and self.index in (501, 502):
                        return 49900
                    return self.index * 100
                raise AssertionError(property)

            def grab(self):
                self.index += 1
                return self.index < 1001

            def retrieve(self):
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            def release(self):
                pass

        for mode in ("duplicate", "backwards", "excess"):
            with patch("ml.extract.cv2.VideoCapture", return_value=Capture(mode)), \
                    patch("ml.extract.FaceLandmarkDetector") as detector:
                detector.return_value.process.return_value = []
                if mode == "duplicate":
                    result = extract_video("fixture", FeatureConfig(), allow_duplicate_pts=True)
                    self.assertEqual(result["duplicate_pts_skipped"], 1)
                    self.assertEqual(result["decoded_frames"], 1001)
                    pts = [call.kwargs["timestamp_ms"] for call in detector.return_value.process.call_args_list]
                    self.assertTrue(all(a < b for a, b in zip(pts, pts[1:])))
                else:
                    with self.assertRaises(ValueError):
                        extract_video("fixture", FeatureConfig(), allow_duplicate_pts=True)

    def test_real_mediapipe_on_blank_video_produces_no_training_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "blank.mp4"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
            self.assertTrue(writer.isOpened())
            for _ in range(25):
                writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
            writer.release()
            result = extract_video(path, FeatureConfig(window_seconds=2, stride_seconds=1))
            self.assertEqual(result["rows"], [])
            self.assertEqual(result["candidate_windows"], 1)
            self.assertEqual(result["rejected_windows"], 1)

    def test_parallel_extraction_keeps_order_and_quality_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subject = root / "raw" / "01"
            subject.mkdir(parents=True)
            for label in (0, 10):
                writer = cv2.VideoWriter(str(subject / f"{label}.mp4"),
                                         cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
                self.assertTrue(writer.isOpened())
                for _ in range(25):
                    writer.write(np.full((64, 64, 3), label, dtype=np.uint8))
                writer.release()
            make_manifest(root / "raw", root / "manifest.csv")
            with self.assertRaisesRegex(ValueError, "No valid feature windows"):
                extract(root / "manifest.csv", root / "features",
                        FeatureConfig(window_seconds=2, stride_seconds=1), workers=2)
            audit = json.loads((root / "features" / "extraction.json").read_text())
            self.assertEqual([v["video_id"] for v in audit["videos"]], ["uta-01-0", "uta-01-10"])
            self.assertEqual([v["rejected_windows"] for v in audit["videos"]], [1, 1])


def synthetic_features(root):
    """Exercise the pipeline, never serve as evidence of model quality."""
    config = FeatureConfig(sample_hz=4)
    rows, videos = [], []
    for subject in range(10):
        for label in (0, 1):
            video_id = f"fixture-{subject}-{label}"
            video_hash = hashlib.sha256(video_id.encode()).hexdigest()
            window = FeatureWindow(config)
            count = 0
            for tick in range(65):
                now = tick / 4
                ear = (0.12 if label else 0.32) + subject * 0.001
                window.add(now, ear, {"yaw": subject * 0.01, "pitch": 0.1})
                if now >= 10 and tick % 8 == 0:
                    snapshot = window.snapshot()
                    if snapshot:
                        count += 1
                        rows.append({"subject_id": str(subject), "video_id": video_id,
                                     "video_sha256": video_hash, "label": label,
                                     "start_s": snapshot["start_s"], "end_s": snapshot["end_s"],
                                     "coverage": snapshot["coverage"], "baseline_prediction": label,
                                     **snapshot["features"]})
            videos.append({"subject_id": str(subject), "video_id": video_id,
                           "video_sha256": video_hash, "label": "DROWSY" if label else "ALERT",
                           "accepted_windows": count, "label_source": "SYNTHETIC TEST FIXTURE ONLY"})
    path = root / "features.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    (root / "extraction.json").write_text(json.dumps({"feature_version": FEATURE_VERSION,
        "feature_config": asdict(config), "features_sha256": sha256_file(path), "videos": videos,
        "landmarker_sha256": sha256_file(TASK_PATH), "mediapipe_version": mp.__version__}), encoding="utf-8")
    return path


class TrainingTests(unittest.TestCase):
    def test_group_split_disjoint_and_metadata_never_model_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = synthetic_features(Path(temporary))
            frame, _ = load_features(path)
            indices, _ = split_subjects(frame)
            groups = [set(frame.iloc[index].subject_id) for index in indices.values()]
            self.assertEqual([len(group) for group in groups], [6, 2, 2])
            self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
            self.assertFalse({"label", "subject_id", "video_id", "start_s", "end_s", "coverage"} & set(FEATURE_NAMES))
            with self.assertRaises(ValueError):
                split_subjects(frame[frame.subject_id.isin(["0", "1", "2"])])
            path.write_text(path.read_text() + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_features(path)

    def test_train_artifacts_scaled_train_only_and_live_feature_parity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = synthetic_features(root)
            report = train(path, root / "run")
            self.assertIn(report["selected_kind"], ("rf", "svm"))
            svm = joblib.load(root / "run" / "svm.joblib")
            frame, _ = load_features(path)
            indices, _ = split_subjects(frame)
            train_mean = frame.iloc[indices["train"]][list(FEATURE_NAMES)].mean().to_numpy()
            np.testing.assert_allclose(svm["estimator"].named_steps["standardscaler"].mean_, train_mean)
            model = DrowsinessModel(root / "run" / "selected.joblib")
            with patch("ml.train.score_model", wraps=score_model) as score:
                for tick in range(41):
                    prediction = model.update(tick / 4, 0.12, {"yaw": 0.0, "pitch": 0.1})
                self.assertIn(prediction, (0, 1))
                self.assertEqual(score.call_count, 1)
                np.testing.assert_allclose(score.call_args.args[1][0], frame.iloc[4][list(FEATURE_NAMES)].to_numpy(dtype=float))
            diagnostic = model.last_diagnostics
            self.assertEqual(diagnostic["prediction"], prediction)
            self.assertEqual(diagnostic["model_version"], model.model_version)
            self.assertEqual(diagnostic["feature_version"], FEATURE_VERSION)
            self.assertEqual(diagnostic["score"], model.last_score)
            self.assertEqual(diagnostic["end_s"], 10)
            self.assertEqual(diagnostic["start_s"], 0)
            json.dumps(diagnostic, allow_nan=False)
            # A cached prediction must not masquerade as a new inference record.
            self.assertEqual(model.update(10.125, 0.12, POSE), prediction)
            self.assertIsNone(model.last_diagnostics)
            self.assertEqual(model.last_score, diagnostic["score"])
            self.assertIsNone(model.update(10.25))
            self.assertIsNone(model.last_score)
            self.assertIsNone(model.last_diagnostics)
            self.assertIsNone(model.update(15, 0.12, POSE))
            selected = joblib.load(root / "run" / "selected.joblib")
            # Gap-free synthetic training values are identical between v2/v3.
            legacy = {**selected, "feature_version": LEGACY_FEATURE_VERSION}
            joblib.dump(legacy, root / "legacy.joblib")
            self.assertIsInstance(DrowsinessModel(root / "legacy.joblib").window, LegacyFeatureWindow)
            selected["feature_names"] = list(reversed(FEATURE_NAMES))
            joblib.dump(selected, root / "incompatible.joblib")
            with self.assertRaises(ValueError):
                DrowsinessModel(root / "incompatible.joblib")
            with self.assertRaises(ValueError):
                train(path, root / "run")
            self.assertTrue((root / "run" / "confusion_baseline.json").exists())
            self.assertTrue((root / "run" / "comparison.md").exists())
            self.assertEqual(report["data_quality"]["source_subjects"], 10)
            self.assertEqual(report["data_quality"]["source_videos"], 20)
            plot_report(root / "run")
            self.assertTrue((root / "run" / "confusion_matrices.png").read_bytes().startswith(b"\x89PNG"))
            self.assertTrue((root / "run" / "test_metrics.png").read_bytes().startswith(b"\x89PNG"))

    def test_fusion_unknown_and_distraction_not_overwritten_by_alert_class(self):
        distracted = {"valid": True, "calibrating": False, "is_distracted": True}
        self.assertEqual(fuse_state(None, distracted), "DISTRACTED")
        self.assertEqual(fuse_state(None, {**distracted, "valid": False}), "UNKNOWN")
        self.assertEqual(fuse_state(None, {**distracted, "calibrating": True}), "UNKNOWN")
        self.assertEqual(fuse_state(None, {**distracted, "is_distracted": False}), "UNKNOWN")
        self.assertEqual(fuse_state(None, None), "UNKNOWN")
        self.assertEqual(fuse_state(0, distracted), "DISTRACTED")
        self.assertEqual(fuse_state(1, distracted), "DROWSY")
        self.assertEqual(fuse_state(0, {"valid": True, "calibrating": False}), "ATTENTIVE")
        self.assertEqual(fuse_state(0, {"valid": True, "calibrating": True}), "UNKNOWN")
        self.assertIsNone(load_optional_model("baseline", "unused"))
        with self.assertLogs("ml.runtime", level="ERROR"):
            self.assertIsNone(load_optional_model("ml", "does-not-exist.joblib"))

    def test_runtime_failure_never_returns_stale_prediction(self):
        model = DrowsinessModel.__new__(DrowsinessModel)
        model.failed, model.prediction = False, 1
        model.last_score, model.last_diagnostics = 0.9, {"prediction": 1}
        model.window = Mock()
        model.window.add.side_effect = ValueError("bad observation")
        with self.assertLogs("ml.runtime", level="ERROR"):
            self.assertIsNone(model.update(10, 0.1, POSE))
        self.assertTrue(model.failed)
        self.assertIsNone(model.last_score)
        self.assertIsNone(model.last_diagnostics)
        self.assertIsNone(model.update(11, 0.1, POSE))

    def test_actual_loaded_version_is_used_in_status_and_telemetry(self):
        client = MQTTClient.__new__(MQTTClient)
        client.model_version = "rf-uta-test-version"
        self.assertEqual(json.loads(client._build_status_payload("ONLINE"))["model_version"],
                         "rf-uta-test-version")
        state = {"confirmed_state": "DROWSY", "candidate_state": "DROWSY",
                 "model_version": "rf-uta-test-version"}
        with patch.object(publisher, "send_message") as send:
            publisher.publish_telemetry(client, state, True, 0.1, 0.8, True, POSE)
        self.assertEqual(send.call_args.args[2]["model_version"], "rf-uta-test-version")

    def test_main_uses_optional_model_without_bypassing_existing_confirmation(self):
        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        camera = Mock()
        camera.isOpened.return_value = True
        camera.read.return_value = (True, frame)
        model = SimpleNamespace(model_version="rf-test", update=Mock(return_value=1), last_inference_ms=0.1,
                                last_diagnostics=None, last_score=.8, kind="rf", threshold=.5,
                                config=FeatureConfig())
        policy = app.AlertPolicy("vision-test", "rf-test")
        policy.update = Mock(wraps=policy.update)
        with patch.object(app, "load_optional_model", return_value=model), \
                patch.object(app, "AI_EYE_CLOSURE_GUARD_ENABLED", True), \
                patch.object(app, "AI_EYE_CLOSURE_CALIBRATION", "local-approved-report.json"), \
                patch.object(app, "load_threshold", return_value=.25) as calibration, \
                patch.object(app, "AI_DEBUG_PREDICTIONS", True), \
                patch.object(app, "init_db", return_value=True), \
                patch.object(app, "VideoUploadWorker"), patch.object(app, "LocalAlertWorker"), \
                patch.object(app.cv2, "VideoCapture", return_value=camera), \
                patch.object(app.cv2, "imshow"), patch.object(app.cv2, "destroyAllWindows"), \
                patch.object(app.cv2, "waitKey", side_effect=[-1, ord("q")]), \
                patch.object(app, "FaceLandmarkDetector") as detector, \
                patch.object(app, "calculate_average_ear", return_value=0.1), \
                patch.object(app, "HeadPoseEstimator") as head, \
                patch.object(app, "MQTTClient") as mqtt, \
                patch.object(app, "AlertPolicy", return_value=policy), patch.object(app, "RuntimeMetrics"), \
                patch.object(app, "publish_event"), patch.object(app, "publish_telemetry"):
            detector.return_value.process.return_value = [[None]]
            head.return_value.estimate.return_value = POSE
            app.main()
        self.assertEqual(model.update.call_count, 2)
        calibration.assert_called_once_with("local-approved-report.json", app.DEVICE_CODE)
        self.assertEqual(model.config.ear_threshold, .20)
        self.assertEqual([call.args[0] for call in policy.update.call_args_list], ["DROWSY", "DROWSY"])
        mqtt.assert_called_once_with(model_version="rf-test")
        camera.release.assert_called_once()

    def test_degenerate_landmarks_are_missing_observations_in_live_pipeline(self):
        frame = np.zeros((32, 64, 3), dtype=np.uint8)
        camera = Mock()
        camera.isOpened.return_value = True
        camera.read.return_value = (True, frame)
        policy = app.AlertPolicy("vision-test", "baseline-test")
        policy.update = Mock(wraps=policy.update)
        with patch.object(app, "load_optional_model", return_value=None), \
                patch.object(app, "init_db", return_value=True), \
                patch.object(app, "VideoUploadWorker"), patch.object(app, "LocalAlertWorker"), \
                patch.object(app.cv2, "VideoCapture", return_value=camera), \
                patch.object(app.cv2, "imshow"), patch.object(app.cv2, "destroyAllWindows"), \
                patch.object(app.cv2, "waitKey", return_value=ord("q")), \
                patch.object(app, "FaceLandmarkDetector") as detector, \
                patch.object(app, "calculate_average_ear", return_value=float("nan")) as ear, \
                patch.object(app, "HeadPoseEstimator") as head, \
                patch.object(app, "EyeClosureTracker") as eyes, \
                patch.object(app, "MQTTClient"), \
                patch.object(app, "AlertPolicy", return_value=policy), patch.object(app, "RuntimeMetrics"), \
                patch.object(app, "create_video_writer", return_value=(None, None)), \
                patch.object(app, "publish_event"), patch.object(app, "publish_telemetry"):
            detector.return_value.process.return_value = [[None]]
            head.return_value.estimate.return_value = POSE
            app.main()
        ear.assert_called_once_with([None], (64, 32))
        head.return_value.estimate.assert_called_once_with([None], (64, 32))
        eyes.return_value.update.assert_not_called()
        self.assertEqual(policy.update.call_args.args[0], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
