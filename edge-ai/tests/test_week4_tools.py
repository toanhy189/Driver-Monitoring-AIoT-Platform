from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.dataset import sha256_file
from ml.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig
from ml.runtime import DrowsinessModel, fuse_state
from ml.week4 import prepare_states, train_states, compare_rules
from service.runtime_metrics import RuntimeMetrics
from ml.evaluate_events import evaluate


class Week4ToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self):
        rows, intervals = [], []
        for person, split in enumerate(("train", "validation", "test")):
            for state_index, state in enumerate(("ATTENTIVE", "DISTRACTED", "DROWSY")):
                video = f"person-{person}-video-{state_index}"
                digest = f"{person+1:02d}{state_index+1:02d}"+"a"*60
                for number in range(5):
                    rows.append({"subject_id": str(person), "video_id": video, "video_sha256": digest,
                        "start_s": number*20, "end_s": (number+1)*20, "label": 999,
                        **{name: float(state_index)+number/100 for name in FEATURE_NAMES}})
                intervals.append(dict(subject_id=str(person), video_id=video, video_sha256=digest,
                    start_s=0, end_s=100, state=state, reviewer="unit-test fixture", source="synthetic data, not evidence",
                    label_method="manual_review", split=split))
        features, labels = self.root/"features.csv", self.root/"labels.csv"
        pd.DataFrame(rows).to_csv(features, index=False)
        pd.DataFrame(intervals).to_csv(labels, index=False)
        (self.root/"extraction.json").write_text(json.dumps({"feature_version": FEATURE_VERSION,
            "feature_config": asdict(FeatureConfig(window_seconds=20)), "features_sha256": sha256_file(features)}))
        return features, labels

    def test_independent_annotations_replace_binary_labels_and_keep_twenty_second_schema(self):
        features, labels = self.fixture()
        output = self.root/"reviewed.csv"
        rows = prepare_states([features], labels, output)
        self.assertEqual(set(rows.label), {0,1,2})
        self.assertEqual(json.loads(output.with_suffix(".audit.json").read_text())["feature_config"]["window_seconds"], 20)
        self.assertEqual(set(pd.read_csv(features).label), {999})

    def test_person_leakage_and_prediction_generated_labels_are_rejected(self):
        features, labels = self.fixture()
        data = pd.read_csv(labels)
        data.loc[0, "subject_id"] = data.loc[3, "subject_id"]
        data.to_csv(labels, index=False)
        with self.assertRaisesRegex(ValueError, "person"):
            prepare_states([features], labels, self.root/"bad.csv")
        features, labels = self.fixture()
        data = pd.read_csv(labels)
        data.loc[0, "label_method"] = "rule_prediction"
        data.to_csv(labels, index=False)
        with self.assertRaisesRegex(ValueError, "predictions"):
            prepare_states([features], labels, self.root/"bad.csv")

    def test_changed_feature_cache_and_binary_only_labels_are_rejected(self):
        features, labels = self.fixture()
        features.write_text(features.read_text()+"\n")
        with self.assertRaisesRegex(ValueError, "audit"):
            prepare_states([features], labels, self.root/"bad.csv")
        features, labels = self.fixture()
        data = pd.read_csv(labels)
        data["state"] = "DROWSY"
        data.to_csv(labels, index=False)
        with self.assertRaisesRegex(ValueError, "three"):
            prepare_states([features], labels, self.root/"bad.csv")

    def test_three_class_artifact_can_load_without_promoting_existing_model(self):
        features, labels = self.fixture()
        reviewed = self.root/"reviewed.csv"
        prepare_states([features], labels, reviewed)
        report = train_states(reviewed, self.root/"new-run")
        self.assertEqual(set(report["models"]), {"rf", "svm"})
        model = DrowsinessModel(self.root/"new-run/selected.joblib")
        self.assertTrue(model.multiclass)
        self.assertEqual(model.config.window_seconds, 20)
        self.assertEqual(fuse_state("DISTRACTED", {"valid":True, "calibrating":False}), "DISTRACTED")
        self.assertEqual(fuse_state("ATTENTIVE", {"valid":False}), "UNKNOWN")

    def test_runtime_metrics_measure_actual_stage_and_fps_without_a_camera(self):
        now = [0.0]
        metric = RuntimeMetrics(self.root/"performance.jsonl", clock=lambda: now[0])
        for value in (1, 2, 9):
            metric.observe("estimator", value)
            metric.frame()
            now[0] += 0.1
        with patch("service.runtime_metrics.rss_bytes", return_value=123):
            result = metric.write(model_version="unit-test")
        self.assertAlmostEqual(result["fps"], 10)
        self.assertEqual(result["stages"]["estimator"]["p95_ms"], 9)
        self.assertEqual(result["rss_bytes"], 123)

    def test_episode_metrics_deduplicate_retries_and_report_actual_onset_delay(self):
        truth = self.root/"truth.csv"
        truth.write_text("session_id,start,end,state\ns,2026-11-07T00:00:00Z,2026-11-07T01:00:00Z,ATTENTIVE\n"
            "s,2026-11-07T01:00:00Z,2026-11-07T01:01:00Z,DROWSY\n", encoding="utf-8")
        events = [dict(message_id="false", session_id="s", episode_id="a", state="DROWSY",
            event_type="DROWSY_THRESHOLD_REACHED", timestamp="2026-11-07T00:00:03Z", observed_at="2026-11-07T00:00:03Z"),
            dict(message_id="real", session_id="s", episode_id="b", state="DROWSY",
            event_type="DROWSY_THRESHOLD_REACHED", timestamp="2026-11-07T01:00:05Z", observed_at="2026-11-07T01:00:05Z")]
        path = self.root/"events.jsonl"
        path.write_text("\n".join(json.dumps(event) for event in events+[events[0]]), encoding="utf-8")
        report = evaluate(path, truth)
        self.assertEqual(report["false_warning_episodes_per_attentive_hour"], 1)
        self.assertEqual(report["detected_intervals"], 1)
        self.assertEqual(report["ai_detection_delay_seconds"][0]["delay_s"], 5)


if __name__ == "__main__":
    unittest.main()
