"""Geometry invariance, temporal features and grouped-selection regressions."""

from dataclasses import asdict
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from eye import calculate_ear
from head_pose import HeadPoseEstimator
from ml.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig, FeatureWindow
from ml.dataset import sha256_file
from ml.optimize import grouped_folds, optimize, selection_rank, thin_training_rows
from ml.rewindow import rewindow
from ml.runtime import DrowsinessModel
from ml.plot_report import plot_report
from ml.train import split_subjects
from test_ml import synthetic_features


def landmarks(points, size):
    width, height = size
    return [SimpleNamespace(x=x / width, y=y / height) for x, y in points]


class GeometryTests(unittest.TestCase):
    def test_same_eye_geometry_in_portrait_landscape_and_scaled_image(self):
        points = [(30, 50), (40, 45), (50, 45), (60, 50), (50, 55), (40, 55)]
        expected = 1 / 3
        for size in ((100, 200), (200, 100), (100, 100)):
            self.assertAlmostEqual(calculate_ear(landmarks(points, size), range(6), size), expected)
        scaled = [(x * 2, y * 2) for x, y in points]
        self.assertAlmostEqual(calculate_ear(landmarks(scaled, (400, 200)), range(6), (400, 200)), expected)

    def test_head_ratios_invariant_to_canvas_aspect_and_uniform_scale(self):
        points = [(50, 50)] * 468
        for i, p in {1: (55, 50), 263: (30, 40), 33: (70, 40), 10: (50, 10),
                     152: (50, 90), 61: (40, 65), 291: (60, 65)}.items():
            points[i] = p
        head = HeadPoseEstimator()
        reference = head.estimate(landmarks(points, (100, 200)), (100, 200))
        for size in ((200, 100), (100, 100)):
            self.assertEqual(head.estimate(landmarks(points, size), size), reference)

    def test_completed_eye_closures_and_causal_features(self):
        config = FeatureConfig(window_seconds=5, stride_seconds=1, sample_hz=10)
        window = FeatureWindow(config)
        for tick in range(51):
            now = tick / 10
            ear = 0.1 if 1 <= now < 1.3 or 3 <= now < 3.5 else 0.3
            window.add(now, ear, {"yaw": 0, "pitch": .1})
        f = window.snapshot()["features"]
        self.assertEqual(set(f), set(FEATURE_NAMES))
        self.assertAlmostEqual(f["closed_episodes_per_min"], 24)
        self.assertAlmostEqual(f["closed_duration_mean_s"], .4)
        self.assertAlmostEqual(f["closed_duration_std_s"], .1)
        self.assertGreater(f["ear_closing_speed_p90"], 0)
        self.assertTrue(np.isfinite(list(f.values())).all())
        # A closure interrupted by missing data is never counted as complete.
        broken = FeatureWindow(config)
        for tick in range(51):
            now = tick / 10
            broken.add(now, None if tick == 12 else (.1 if 1 <= now < 1.5 else .3),
                       {"yaw": 0, "pitch": .1})
        self.assertEqual(broken.snapshot()["features"]["closed_episodes_per_min"], 0)


class OptimizationTests(unittest.TestCase):
    def test_group_folds_exclude_historical_test_and_training_windows_do_not_overlap(self):
        with tempfile.TemporaryDirectory() as folder:
            frame = pd.read_csv(synthetic_features(Path(folder)), dtype={"subject_id": str})
            development = list(map(str, range(8)))
            dev, folds = grouped_folds(frame, development, ["8", "9"], n_splits=4)
            self.assertEqual(set(dev.subject_id), set(development))
            validation_people = []
            for train, valid in folds:
                a, b = set(dev.iloc[train].subject_id), set(dev.iloc[valid].subject_id)
                self.assertFalse(a & b)
                self.assertFalse((a | b) & {"8", "9"})
                validation_people.extend(b)
                retained = thin_training_rows(dev.iloc[train], 10)
                self.assertTrue(set(retained).issubset(set(train)))
                for _, rows in dev.loc[retained].groupby("video_id"):
                    self.assertTrue((np.diff(rows.end_s) >= 10 - 1e-8).all())
            self.assertCountEqual(validation_people, development)

    def test_test_feature_changes_cannot_change_grouped_selection_or_scaler(self):
        specs = [("rf", {"n_estimators": 5}, RandomForestClassifier(n_estimators=5, random_state=42)),
                 ("svm", {"C": 1.}, make_pipeline(StandardScaler(), SVC(C=1.)))]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            a, b = synthetic_features(first), synthetic_features(second)
            frame = pd.read_csv(a, dtype={"subject_id": str})
            indices, _ = split_subjects(frame)
            split = {name: sorted(set(frame.iloc[idx].subject_id)) for name, idx in indices.items()}
            plan = root / "plan.json"
            plan.write_text(json.dumps({"planned_subject_split": split}), encoding="utf-8")
            changed = pd.read_csv(b, dtype={"subject_id": str})
            changed.loc[changed.subject_id.isin(split["test"]), list(FEATURE_NAMES)] += 1000
            changed.to_csv(b, index=False)
            metadata = json.loads(b.with_name("extraction.json").read_text())
            metadata["features_sha256"] = sha256_file(b)
            b.with_name("extraction.json").write_text(json.dumps(metadata), encoding="utf-8")
            report_a = optimize([a], plan, root / "run-a", n_splits=2, candidate_specs=specs)
            report_b = optimize([b], plan, root / "run-b", n_splits=2, candidate_specs=specs)
            self.assertEqual(report_a["selected_kind"], report_b["selected_kind"])
            for kind in ("rf", "svm"):
                for key in ("window_seconds", "feature_group", "parameters", "threshold", "cv_mean_person"):
                    self.assertEqual(report_a["models"][kind][key], report_b["models"][kind][key])
            artifact = joblib.load(root / "run-a" / "svm.joblib")
            dev = frame[~frame.subject_id.isin(split["test"])].reset_index(drop=True)
            retained = thin_training_rows(dev, 10)
            expected = dev.loc[retained, artifact["feature_names"]].mean().to_numpy()
            np.testing.assert_allclose(artifact["estimator"].named_steps["standardscaler"].mean_, expected)
            DrowsinessModel(root / "run-a" / "selected.joblib")
            self.assertEqual(report_a["reload_check_matching_predictions"], len(indices["test"]))
            plot_report(root / "run-a")
            self.assertTrue((root / "run-a" / "cv_ablation.png").read_bytes().startswith(b"\x89PNG"))
            self.assertTrue((root / "run-a" / "threshold_tradeoff.png").read_bytes().startswith(b"\x89PNG"))
            with self.assertRaises(ValueError):
                optimize([a], plan, root / "run-a", candidate_specs=specs)
            # A feasible candidate outranks one with slightly better F1 but high FPR.
            base = {"macro_f1": .7, "std_person_macro_f1": .1, "drowsy_recall": .8, "false_positive_rate": .2}
            self.assertGreater(selection_rank(base), selection_rank({**base, "macro_f1": .8, "false_positive_rate": .4}))

    def test_rewindow_common_endpoints_match_the_live_window(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = FeatureConfig(sample_hz=2)
            observations = [[tick / 2, .1 if 21 <= tick / 2 < 22 else .3, .1, .2] for tick in range(57)]
            (root / "cache.json").write_text(json.dumps({"observations": observations}), encoding="utf-8")
            (root / "extraction.json").write_text(json.dumps({"feature_version": FEATURE_VERSION,
                "feature_config": asdict(config), "videos": [{"subject_id": "01", "video_id": "v",
                    "cache": "cache.json", "video_sha256": "a" * 64, "label": "ALERT"}]}), encoding="utf-8")
            paths = rewindow(root, root / "out")
            frames = {s: pd.read_csv(path) for s, path in paths.items()}
            for s, table in frames.items():
                np.testing.assert_array_equal(table.end_s, frames[10].end_s)
                window = FeatureWindow(FeatureConfig(**{**asdict(config), "window_seconds": s}))
                expected = []
                for now, ear, yaw, pitch in observations:
                    window.add(now, ear, {"yaw": yaw, "pitch": pitch})
                    if now in set(table.end_s):
                        expected.append(list(window.snapshot()["features"].values()))
                np.testing.assert_allclose(table[list(FEATURE_NAMES)], expected, atol=1e-12)
            observations[42][2] = None
            (root / "cache.json").write_text(json.dumps({"observations": observations}), encoding="utf-8")
            with patch("ml.rewindow.BaselineReplay") as replay:
                replay.return_value.update.return_value = 0
                rewindow(root, root / "missing-out")
                self.assertIn(((21.0, None), {}), [(c.args, c.kwargs) for c in replay.return_value.update.call_args_list])


if __name__ == "__main__":
    unittest.main()
