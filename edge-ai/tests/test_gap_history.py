"""Missing observations interrupt continuity without discarding valid history."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from ml.features import (FEATURE_VERSION, LEGACY_FEATURE_VERSION, FeatureConfig,
                         FeatureWindow, LegacyFeatureWindow, window_for_version)
from ml.runtime import DrowsinessModel

POSE = {"yaw": .1, "pitch": .2}


class GapHistoryTests(unittest.TestCase):
    def test_short_face_loss_preserves_history_but_breaks_closure(self):
        config = FeatureConfig(window_seconds=20)
        current, old = FeatureWindow(config), LegacyFeatureWindow(config)
        for tick in range(201):
            now = tick/10
            missing = 90 <= tick < 100
            for window in (current, old):
                window.add(now, None if missing else .1, None if missing else POSE)
        result = current.snapshot()
        self.assertAlmostEqual(result["coverage"], .945)
        self.assertAlmostEqual(result["features"]["perclos"], 1.)
        self.assertAlmostEqual(result["features"]["longest_closed_s"], 10.)
        self.assertEqual(result["features"]["closed_episodes_per_min"], 0)
        self.assertIsNone(old.snapshot())

    def test_gap_with_no_intermediate_frames_is_never_added_to_closure(self):
        window = FeatureWindow(FeatureConfig(window_seconds=20))
        for now in [*(tick/10 for tick in range(91)), *(tick/10 for tick in range(110, 201))]:
            window.add(now, .1, POSE)
        result = window.snapshot()
        self.assertAlmostEqual(result["coverage"], .9)
        self.assertAlmostEqual(result["features"]["longest_closed_s"], 9.)
        self.assertAlmostEqual(result["features"]["perclos"], 1.)

    def test_over_20_percent_missing_remains_unknown(self):
        window = FeatureWindow(FeatureConfig(window_seconds=20))
        for tick in range(201):
            missing = 70 <= tick < 120
            window.add(tick/10, None if missing else .1, None if missing else POSE)
        self.assertIsNone(window.snapshot())
        self.assertEqual(window.last_quality_reason, "insufficient_valid_coverage")

    def test_current_missing_nan_and_stale_observations_remain_unknown(self):
        window = FeatureWindow(FeatureConfig(window_seconds=20))
        for tick in range(201):
            window.add(tick/10, .3, POSE)
        self.assertIsNone(window.snapshot(20.6))
        window.add(20.1, float("nan"), POSE)
        self.assertIsNone(window.snapshot())
        window.add(20.2, .3, {"yaw": None, "pitch": .2})
        self.assertIsNone(window.snapshot())
        window.add(20.3, .3, POSE)
        self.assertIsNotNone(window.snapshot())

    def test_extended_face_loss_evicts_old_samples_and_requires_coverage(self):
        window = FeatureWindow(FeatureConfig(window_seconds=20))
        for tick in range(201):
            window.add(tick/10, .1, POSE)
        for tick in range(201, 501):
            window.add(tick/10)
        self.assertGreaterEqual(window.samples[0].timestamp, 30.)
        window.add(50.1, .3, POSE)
        self.assertIsNone(window.snapshot())
        for tick in range(502, 702):
            window.add(tick/10, .3, POSE)
        self.assertAlmostEqual(window.snapshot()["features"]["perclos"], 0.)

    def test_version_dispatch_preserves_legacy_gap_free_features(self):
        config = FeatureConfig(window_seconds=20)
        current = window_for_version(FEATURE_VERSION, config)
        old = window_for_version(LEGACY_FEATURE_VERSION, config)
        self.assertIsInstance(old, LegacyFeatureWindow)
        with self.assertRaises(ValueError):
            window_for_version("future-unknown-version", config)
        for tick in range(251):
            for window in (current, old):
                window.add(tick/10, .1 if tick % 20 < 3 else .3, POSE)
        self.assertEqual(current.snapshot(), old.snapshot())

    def test_live_runtime_recovers_without_cached_prediction_on_missing_frames(self):
        model = DrowsinessModel.__new__(DrowsinessModel)
        model.model_version, model.feature_version = "test-gap-history", FEATURE_VERSION
        model.failed, model.prediction = False, None
        model.multiclass = False
        model.config = FeatureConfig(window_seconds=20)
        model.window = FeatureWindow(model.config)
        model.next_prediction = model.last_seen = None
        model.estimator, model.kind, model.threshold = object(), "rf", .5
        from ml.features import FEATURE_NAMES
        model.feature_names = list(FEATURE_NAMES)
        with patch("ml.train.score_model", return_value=np.array([.8])):
            for tick in range(201):
                prediction = model.update(tick/10, .1, POSE)
            self.assertEqual(prediction, 1)
            for tick in range(201, 211):
                self.assertIsNone(model.update(tick/10))
            self.assertEqual(model.update(21.1, .1, POSE), 1)
            for tick in range(212, 512):
                self.assertIsNone(model.update(tick/10))
            self.assertIsNone(model.update(51.2, .1, POSE))


if __name__ == "__main__":
    unittest.main()
