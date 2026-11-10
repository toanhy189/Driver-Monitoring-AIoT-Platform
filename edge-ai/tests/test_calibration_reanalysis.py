from pathlib import Path
import csv
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reanalyze_eye_calibration import reanalyze
from service.eye_calibration import geometry_hashes
from service.eye_closure_guard import EyeClosureGuard
from service.multisignal_calibration import load_profile


class ReanalysisTests(unittest.TestCase):
    def source(self, root):
        source = root/"source"
        source.mkdir()
        metadata = {"format": "eye-guard-calibration-v4", "status": "REJECTED",
                    "geometry_hashes": geometry_hashes(), "guard_version": EyeClosureGuard.VERSION,
                    "device_code": "v", "condition": "glasses", "profile_id": "operator",
                    "camera_index": 0, "frame_size": [640, 480], "capture_completed": True}
        (source/"report.json").write_text(json.dumps(metadata))
        with (source/"observations.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("phase", "elapsed_s", "ear", "yaw", "pitch"))
            writer.writeheader()
            for phase, seconds, ear in (("open_fit", 8, .30), ("closed_fit", 8, .20),
                                        ("open_validation", 30, .30), ("closed_validation", 8, .21)):
                for i in range(seconds*10+1):
                    writer.writerow(dict(phase=phase, elapsed_s=i*.1, ear=ear, yaw=.02, pitch=.19))
        return source

    def test_reanalysis_preserves_rejected_source_and_creates_separate_bound_trial_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = self.source(root); output = root/"v5"
            before = {p.name: p.read_bytes() for p in source.iterdir()}
            report = reanalyze(source, output, closed_actions_confirmed=True)
            self.assertEqual(report["status"], "READY_FOR_TRIAL")
            self.assertAlmostEqual(report["candidate_threshold"], .25)
            self.assertEqual(report["release_status"], "DEVELOPMENT_REANALYSIS_FRESH_TRIAL_REQUIRED")
            self.assertEqual(report["source_report_sha256"], hashlib.sha256(before["report.json"]).hexdigest())
            self.assertEqual(before, {p.name: p.read_bytes() for p in source.iterdir()})
            self.assertEqual((output/"observations.csv").read_bytes(), before["observations.csv"])
            loaded = load_profile(output/"report.json", device_code="v", profile_id="operator",
                                  camera=0, condition="glasses")
            self.assertTrue(loaded["user_confirmed_closed_actions"])
            with self.assertRaisesRegex(ValueError, "new output"):
                reanalyze(source, output)

    def test_reanalysis_cannot_bypass_a_failed_fresh_trial_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = self.source(root)
            review = {"format": "eye-guard-trial-review-v1", "status": "FAILED",
                      "calibration_sha256": hashlib.sha256((source/"report.json").read_bytes()).hexdigest()}
            (source/"fresh-trial-review.json").write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError, "failed a reviewed fresh trial"):
                reanalyze(source, root/"v5")
            self.assertFalse((root/"v5").exists())

    def test_reanalysis_rejects_measurements_with_different_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = self.source(root)
            path = source/"report.json"; report = json.loads(path.read_text())
            report["geometry_hashes"] = {}
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "changed geometry"):
                reanalyze(source, root/"v5")
            self.assertFalse((root/"v5").exists())


if __name__ == "__main__": unittest.main()
