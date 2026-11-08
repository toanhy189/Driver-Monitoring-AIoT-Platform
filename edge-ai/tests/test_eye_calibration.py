"""Calibration integrity and rejection gates; synthetic data, no webcam."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service.eye_calibration import analyze, load_threshold, phase_statistics


def phase(ear):
    return [{"elapsed_s": tick/10, "ear": ear} for tick in range(51)]


def dataset():
    return {"open_fit": phase(.3), "closed_fit": phase(.15),
            "open_validation": phase(.31), "closed_validation": phase(.14)}


class EyeCalibrationTests(unittest.TestCase):
    def test_cancelled_capture_saves_only_numeric_files_and_releases_camera(self):
        import calibrate_eye_guard as capture
        camera = Mock()
        camera.isOpened.return_value = True
        camera.read.return_value = (True, np.zeros((80, 160, 3), dtype=np.uint8))
        detector = Mock()
        detector.process.return_value = []
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"capture"
            with patch.object(sys, "argv", ["calibrate_eye_guard.py", "--condition", "glasses", "--output", str(output)]), \
                    patch("cv2.VideoCapture", return_value=camera), patch("cv2.namedWindow"), \
                    patch("cv2.imshow"), patch("cv2.waitKey", return_value=ord("q")), \
                    patch("cv2.destroyAllWindows"), \
                    patch("face_detection.FaceLandmarkDetector", return_value=detector):
                capture.main()
            report = json.loads((output/"report.json").read_text())
            self.assertEqual(report["status"], "REJECTED")
            self.assertFalse(report["capture_completed"])
            self.assertEqual({p.name for p in output.iterdir()}, {"report.json", "observations.csv"})
            camera.release.assert_called_once()
            detector.close.assert_called_once()

    def test_fit_then_separate_validation_and_no_automatic_activation(self):
        report = analyze(dataset(), "vision-test", "glasses", capture_completed=True)
        self.assertEqual(report["status"], "READY_FOR_TRIAL")
        self.assertAlmostEqual(report["candidate_threshold"], .225)
        self.assertFalse(report["threshold_applied"])
        self.assertEqual(report["scope"], "One-session eye-closure calibration; not drowsiness or new-person acceptance")

    def test_validation_does_not_move_fitted_threshold_to_make_a_pass(self):
        rows = dataset()
        fitted = analyze(rows, "v", "glasses", capture_completed=True)["candidate_threshold"]
        rows["open_validation"] = phase(.17)
        report = analyze(rows, "v", "glasses", capture_completed=True)
        self.assertEqual(report["status"], "REJECTED")
        self.assertEqual(report["candidate_threshold"], fitted)
        self.assertTrue(report["validation"]["open"]["guard_activated"])

    def test_natural_blinks_in_open_validation_are_not_prolonged_closure(self):
        rows = dataset()
        for tick in (10, 11, 12, 30, 31, 32):
            rows["open_validation"][tick]["ear"] = .1
        report = analyze(rows, "v", "glasses", capture_completed=True)
        self.assertGreater(report["validation"]["open"]["measured_closed_fraction"], .05)
        self.assertFalse(report["validation"]["open"]["guard_activated"])
        self.assertEqual(report["status"], "READY_FOR_TRIAL")

    def test_overlap_rejects_instead_of_inventing_a_threshold(self):
        rows = dataset()
        rows["closed_fit"] = phase(.29)
        report = analyze(rows, "v", "glasses", capture_completed=True)
        self.assertEqual(report["status"], "REJECTED")
        self.assertNotIn("candidate_threshold", report)

    def test_missing_frames_and_clock_gaps_do_not_count_as_coverage(self):
        rows = dataset()
        for index in range(10, 30):
            rows["closed_fit"][index]["ear"] = None
        self.assertEqual(analyze(rows, "v", "glasses", capture_completed=True)["status"], "REJECTED")
        with self.assertRaises(ValueError):
            phase_statistics([{"elapsed_s": 0, "ear": .2}, {"elapsed_s": 5, "ear": .2}])

    def test_closed_validation_without_detection_is_rejected(self):
        rows = dataset()
        rows["closed_validation"] = phase(.3)
        report = analyze(rows, "v", "glasses", capture_completed=True)
        self.assertEqual(report["status"], "REJECTED")

    def test_cancelled_or_missing_validation_never_loads(self):
        rows = dataset()
        self.assertEqual(analyze(rows, "v", "glasses", capture_completed=False)["status"], "REJECTED")
        del rows["closed_validation"]
        self.assertEqual(analyze(rows, "v", "glasses", capture_completed=True)["status"], "REJECTED")

    def test_loading_rejects_other_device_changed_geometry_and_rejected_reports(self):
        good = analyze(dataset(), "v", "glasses", capture_completed=True)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"calibration.json"
            path.write_text(json.dumps(good), encoding="utf-8")
            self.assertAlmostEqual(load_threshold(path, "v"), .225)
            with self.assertRaises(ValueError):
                load_threshold(path, "another-device")
            for changes in ({"status": "REJECTED"}, {"geometry_hashes": {}},
                            {"capture_completed": False}, {"candidate_threshold": float("nan")},
                            {"format": "eye-guard-calibration-v1"}):
                bad = copy.deepcopy(good)
                bad.update(changes)
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_threshold(path, "v")


if __name__ == "__main__":
    unittest.main()
