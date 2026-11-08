import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location("landmark_metrics",
    Path(__file__).resolve().parents[1]/"benchmark/landmark_metrics.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class LandmarkMetricTests(unittest.TestCase):
    def test_ground_truth_and_predictions_share_the_same_eye_and_mouth_order(self):
        truth = np.array([[70,20], [20,20], [45,40], [60,65], [30,65]])
        prediction = truth[[1,0,2,4,3]]
        self.assertEqual(metrics.nme(prediction, truth), 0)

    def test_common_subset_is_reported_separately_from_detection_rate(self):
        truth = np.array([[20,20], [70,20], [45,40], [30,65], [60,65]])
        result = metrics.evaluate_benchmark([truth, truth], {
            "one": {"predictions":[truth, truth+10], "times":[.01,.02]},
            "two": {"predictions":[truth, None], "times":[.01,.02]}})
        self.assertEqual(result[0]["Common detected images"], 1)
        self.assertEqual(result[0]["NME common (%)"], 0)
        self.assertGreater(result[0]["NME detected (%)"], 0)
        self.assertEqual(result[1]["Detection rate (%)"], 50)
