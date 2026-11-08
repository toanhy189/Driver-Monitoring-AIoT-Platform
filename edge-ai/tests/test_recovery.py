"""Cohort alignment and OOF comparison on synthetic data, not AI evidence."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from ml.dataset import sha256_file
from ml.features import LEGACY_FEATURE_VERSION
from ml.nthu_ablation import run as ablate
from ml.nthu_recovery import compare, indexed, summary
from ml.nthu_train import select, evaluate
from test_ml import synthetic_features


class RecoveryTests(unittest.TestCase):
    def test_window_keys_reject_rounding_collision(self):
        frame = pd.DataFrame({"subject_id": ["a", "a"], "video_id": ["b", "b"],
                              "end_s": [20., 20.0000001]})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            indexed(frame)

    def test_single_class_rates_are_explicitly_undefined(self):
        rows = pd.DataFrame({"label": [1, 1], "subject_id": ["a", "a"]})
        result = summary(rows, [1, 0])
        self.assertIsNone(result["pooled_fpr"])
        self.assertEqual(result["pooled_recall"], .5)
        self.assertIsNone(summary(rows.iloc[:0], []))

    def test_common_and_recovered_are_disjoint_and_use_validation_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = synthetic_features(root)
            original = pd.read_csv(path, dtype={"subject_id": str})
            audit = json.loads(path.with_name("extraction.json").read_text())
            original = original[original.subject_id.isin(list(map(str, range(8))))].copy()
            original["condition"], original["drowsy_fraction"] = "noglasses", original.label
            feature_paths = {}
            for name, rows in (("old", original[original.end_s < 16]), ("new", original)):
                folder = root / name
                folder.mkdir()
                feature_paths[name] = folder / "features.csv"
                rows.to_csv(feature_paths[name], index=False)
                videos = [{**v, "condition": "noglasses",
                    "candidate_windows": 4, "quality_rejected_windows": 1 if name == "old" else 0,
                    "ambiguous_windows": 0, "accepted_windows": 3 if name == "old" else 4}
                    for v in audit["videos"] if v["subject_id"] in set(rows.subject_id)]
                (folder / "extraction.json").write_text(json.dumps({**audit, "videos": videos,
                    "features_sha256": sha256_file(feature_paths[name]), "feature_windows": len(rows),
                    "role": "development", "label_type": "frame_fraction", "manifest_sha256": "synthetic-only",
                    "coverage_by_condition": {"noglasses": {"source_videos": 16}}}))
            plan = {"development_subjects": list(map(str, range(8))), "fresh_heldout_subjects": ["8", "9"],
                    "candidate_search_proposal": {"feature_groups": ["eyes", "full"]}}
            source_plan = root / "source-plan.json"
            source_plan.write_text(json.dumps(plan))
            specs = [("rf", {"n_estimators": 5}, RandomForestClassifier(n_estimators=5, random_state=42)),
                ("svm", {"C": 1}, make_pipeline(StandardScaler(), SVC(C=1)))]
            with patch("ml.nthu_train.candidates", side_effect=lambda: iter(specs)):
                ablate(feature_paths["old"], source_plan, root / "old-run")
            # No gaps in this fixture: old/new numerical features are identical.
            old_audit_path = feature_paths["old"].with_name("extraction.json")
            old_audit = json.loads(old_audit_path.read_text())
            old_audit["feature_version"] = LEGACY_FEATURE_VERSION
            old_audit_path.write_text(json.dumps(old_audit))
            plan.update(heldout_already_inspected=True,
                parent_ablation_report_sha256=sha256_file(root / "old-run/report.json"),
                parent_oof_sha256=sha256_file(root / "old-run/development_oof_predictions.csv"),
                parent_features_sha256=sha256_file(feature_paths["old"]))
            new_plan = root / "new-plan.json"
            new_plan.write_text(json.dumps(plan))
            with patch("ml.nthu_train.candidates", side_effect=lambda: iter(specs)):
                select(feature_paths["new"], new_plan, root / "new-run", "full")
            with self.assertRaisesRegex(ValueError, "Development-only"):
                evaluate(root / "unread-test.csv", new_plan, root / "new-run")
            report = compare(feature_paths["old"], feature_paths["new"], root / "old-run", root / "new-run",
                             new_plan, root / "comparison")
            self.assertEqual(report["common_windows"], 48)
            self.assertEqual(report["recovered_windows"], 16)
            self.assertEqual(report["lost_windows"], 0)
            self.assertEqual(report["feature_delta_on_common"]["common_rows_changed_at_1e_minus_6"], 0)
            output = pd.read_csv(root / "comparison/development_oof_predictions.csv")
            self.assertEqual(output.cohort.value_counts().to_dict(), {"common": 48, "recovered": 16})
            self.assertTrue((root / "comparison/common_windows_confusion.png").read_bytes().startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
