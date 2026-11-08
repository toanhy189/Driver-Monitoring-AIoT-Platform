"""Frame-target alignment, role isolation and selection metrics."""

from pathlib import Path
import csv
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from ml.nthu import window_target, read_manifest
from ml.nthu_train import check_people, person_summary
from ml.nthu_train import select, evaluate
from ml.dataset import sha256_file
from ml.features import FeatureConfig, FeatureWindow, FEATURE_GROUPS
from ml.nthu_diagnostics import rejection_reason
from test_ml import synthetic_features


class FrameLabelsTests(unittest.TestCase):
    def test_pure_and_ambiguous_windows_use_original_frames(self):
        times = np.arange(11, dtype=float)
        self.assertEqual(window_target(times, [0]*11, 0, 10), (0, 0.0))
        self.assertEqual(window_target(times, [1]*11, 0, 10), (1, 1.0))
        label, fraction = window_target(times, [0]*5+[1]*6, 0, 10)
        self.assertEqual(label, -1)
        self.assertAlmostEqual(fraction, 6/11)

    def test_labels_after_window_do_not_change_target(self):
        times = np.arange(21, dtype=float)
        a = [0]*21
        b = [0]*11+[1]*10
        self.assertEqual(window_target(times, a, 0, 10), window_target(times, b, 0, 10))

    def test_misaligned_invalid_and_nonmonotonic_inputs_rejected(self):
        for times, labels in (([0, 1], [0]), ([0, 0, 2], [0, 0, 1]),
                              ([0, 1, 2], [0, 2, 1])):
            with self.assertRaises(ValueError):
                window_target(times, labels, 0, 1)

    def test_manifest_role_mixing_and_quarantine_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.csv"
            rows = [{"video_id": "a", "role": "development", "status": "READY_FOR_FEATURE_EXTRACTION", "video_sha256": "1"},
                    {"video_id": "b", "role": "fresh_heldout", "status": "READY_FOR_FEATURE_EXTRACTION", "video_sha256": "2"}]
            with path.open("w", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "mix"):
                read_manifest(path)


class EvaluationTests(unittest.TestCase):
    def test_select_freezes_before_evaluation_and_artifact_reloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = synthetic_features(root)
            frame = pd.read_csv(original, dtype={"subject_id": str})
            audit = json.loads(original.with_name("extraction.json").read_text())
            plan = {"development_subjects": [str(i) for i in range(8)], "fresh_heldout_subjects": ["8", "9"],
                    "candidate_search_proposal": {"feature_groups": ["eyes", "full"]}}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan))
            paths = {}
            for role, people in (("development", plan["development_subjects"]), ("fresh_heldout", plan["fresh_heldout_subjects"])):
                directory = root / role
                directory.mkdir()
                subset = frame[frame.subject_id.isin(people)].copy()
                subset["condition"], subset["drowsy_fraction"] = "noglasses", subset.label
                path = directory / "features.csv"
                subset.to_csv(path, index=False)
                videos = [{**v, "condition": "noglasses"} for v in audit["videos"] if v["subject_id"] in people]
                path.with_name("extraction.json").write_text(json.dumps({**audit, "videos": videos,
                    "role": role, "label_type": "frame_fraction", "feature_windows": len(subset),
                    "features_sha256": sha256_file(path)}))
                paths[role] = path
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler
            from sklearn.svm import SVC
            specs = [("rf", {"n_estimators": 5}, RandomForestClassifier(n_estimators=5, random_state=42)),
                     ("svm", {"C": 1}, make_pipeline(StandardScaler(), SVC(C=1)))]
            with patch("ml.nthu_train.candidates", side_effect=lambda: iter(specs)):
                select(paths["development"], plan_path, root / "run")
                select(paths["development"], plan_path, root / "full", "full")
            from ml.runtime import DrowsinessModel
            full = DrowsinessModel(root / "full/selected.joblib")
            self.assertEqual(full.feature_names, list(FEATURE_GROUPS["full"]))
            self.assertEqual(json.loads((root / "full/selection-frozen.json").read_text())["folds"],
                             json.loads((root / "run/selection-frozen.json").read_text())["folds"])
            with self.assertRaisesRegex(ValueError, "supports"):
                select(paths["development"], plan_path, root / "invalid", "core")
            from ml.nthu_ablation import run as ablate
            with patch("ml.nthu_train.candidates", side_effect=lambda: iter(specs)):
                ablate(paths["development"], plan_path, root / "ablation")
            comparison = json.loads((root / "ablation/report.json").read_text(encoding="utf-8"))
            self.assertEqual(set(comparison["results"]), {"eyes/rf", "eyes/svm", "full/rf", "full/svm"})
            self.assertEqual(comparison["results"]["full/rf"]["features"], 19)
            self.assertTrue((root / "ablation/development_oof_predictions.csv").exists())
            self.assertTrue((root / "run/selection-frozen.json").exists())
            self.assertFalse((root / "run/report.json").exists())
            evaluate(paths["fresh_heldout"], plan_path, root / "run")
            report = json.loads((root / "run/report.json").read_text())
            self.assertEqual(report["heldout_people"], ["8", "9"])
            with self.assertRaisesRegex(ValueError, "already"):
                evaluate(paths["fresh_heldout"], plan_path, root / "run")

    def test_heldout_people_never_accepted_as_development(self):
        plan = {"development_subjects": [f"d{i}" for i in range(8)], "fresh_heldout_subjects": ["t1", "t2"]}
        frame = pd.DataFrame({"subject_id": [*plan["development_subjects"], "t1"]})
        with self.assertRaisesRegex(ValueError, "leakage"):
            check_people(frame, plan, "development")

    def test_person_weighting_and_undefined_class_rates(self):
        summary = person_summary(np.array([0, 0, 0, 1]), np.array([1, 1, 1, 1]),
                                 np.array(["a", "a", "a", "b"]))
        self.assertAlmostEqual(summary["accuracy"], .5)
        self.assertAlmostEqual(summary["false_positive_rate"], 1.)
        self.assertAlmostEqual(summary["drowsy_recall"], 1.)
        self.assertEqual(summary["people_with_positive_labels"], 1)
        self.assertEqual(summary["people_with_negative_labels"], 1)


class DiagnosticTests(unittest.TestCase):
    def test_rejection_gates_match_shared_window(self):
        window = FeatureWindow(FeatureConfig(window_seconds=2, stride_seconds=1,
                                             face_loss_reset_seconds=10))
        self.assertEqual(rejection_reason(window, 0), "no_history")
        window.add(0, .3, {"yaw": 0, "pitch": 0})
        self.assertEqual(rejection_reason(window, 0), "insufficient_continuous_history")
        for t in np.arange(.1, 2.01, .1):
            window.add(float(t), .3, {"yaw": 0, "pitch": 0})
        self.assertEqual(rejection_reason(window, 2), "accepted_quality")
        self.assertIsNotNone(window.snapshot(2))
        self.assertEqual(rejection_reason(window, 2.6), "stale_current_observation")
        window.add(2.1)
        self.assertEqual(rejection_reason(window, 2.1), "invalid_current_observation")
        self.assertIsNone(window.snapshot())

    def test_coverage_loss_and_reset_are_distinguished(self):
        config = FeatureConfig(window_seconds=2, stride_seconds=1, face_loss_reset_seconds=10)
        window = FeatureWindow(config)
        for t in np.arange(0, 2.01, .1):
            valid = t < .5 or t >= 1.5
            window.add(float(t), .3 if valid else None, {"yaw": 0, "pitch": 0} if valid else None)
        self.assertEqual(rejection_reason(window, 2), "insufficient_valid_coverage")
        self.assertIsNone(window.snapshot(2))
        window = FeatureWindow(FeatureConfig(window_seconds=2, stride_seconds=1))
        window.add(0, .3, {"yaw": 0, "pitch": 0})
        window.add(2, .3, {"yaw": 0, "pitch": 0})
        self.assertEqual(rejection_reason(window, 2), "insufficient_valid_coverage")


if __name__ == "__main__":
    unittest.main()
