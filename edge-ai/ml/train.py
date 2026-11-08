"""Compare the existing binary rule, Random Forest and scaled SVM by subject.

Validation chooses hyperparameters, thresholds and the winner. The held-out test
is reported after selection; it is never passed to fit or threshold selection.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from ml.dataset import sha256_file
from ml.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig

ARTIFACT_FORMAT = 1


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def load_features(path):
    path = Path(path)
    metadata = json.loads(path.with_name("extraction.json").read_text(encoding="utf-8"))
    if metadata["feature_version"] != FEATURE_VERSION or metadata["features_sha256"] != sha256_file(path):
        raise ValueError("Feature version/checksum mismatch; re-extract the videos")
    config = FeatureConfig(**metadata["feature_config"])
    frame = pd.read_csv(path, dtype={"subject_id": str, "video_id": str, "video_sha256": str})
    required = {"subject_id", "video_id", "video_sha256", "label", "start_s", "end_s",
                "coverage", "baseline_prediction", *FEATURE_NAMES}
    if set(frame.columns) != required or frame.empty or frame.isna().any().any():
        raise ValueError("Empty, missing or unexpected feature columns")
    numeric = frame[["start_s", "end_s", "coverage", *FEATURE_NAMES]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or not frame.label.isin([0, 1]).all():
        raise ValueError("Non-finite features or labels outside ALERT=0/DROWSY=1")
    if (not frame.baseline_prediction.isin([-1, 0, 1]).all()
            or not frame.coverage.between(config.min_coverage - 1e-8, 1 + 1e-8).all()
            or not np.allclose(frame.end_s - frame.start_s, config.window_seconds)
            or (frame.start_s < -1e-7).any()
            or frame.duplicated(["video_id", "end_s"]).any()):
        raise ValueError("Invalid quality, window geometry, baseline label or duplicate window")
    audit = {v["video_id"]: v for v in metadata["videos"]}
    if len(audit) != len(metadata["videos"]):
        raise ValueError("Duplicate videos in extraction audit")
    for identifier, rows in frame.groupby("video_id"):
        record = audit.get(identifier)
        if record is None or len(rows) != record["accepted_windows"]:
            raise ValueError("Feature rows do not match the extraction audit")
        if (set(rows.subject_id) != {record["subject_id"]}
                or set(rows.video_sha256) != {record["video_sha256"]}
                or set(rows.label) != {0 if record["label"] == "ALERT" else 1}):
            raise ValueError("Subject/label/video hash does not match the extraction audit")
    if any(rows.subject_id.nunique() != 1 or rows.label.nunique() != 1
           for _, rows in frame.groupby("video_sha256")):
        raise ValueError("The same source video has inconsistent subject IDs or labels")
    return frame, metadata


def split_subjects(frame, seed=42):
    if frame.subject_id.nunique() < 5:
        raise ValueError("Need at least 5 people with both labels for train/validation/test; aim for 20+")
    # Look only at label coverage, never at model performance, when choosing a split.
    for offset in range(100):
        split_seed = seed + offset
        first = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=split_seed)
        development, test = next(first.split(frame, groups=frame.subject_id))
        second = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=split_seed)
        train_relative, validation_relative = next(second.split(frame.iloc[development],
                                                  groups=frame.iloc[development].subject_id))
        indices = {"train": development[train_relative], "validation": development[validation_relative],
                   "test": test}
        if all(set(frame.iloc[index].label) == {0, 1} for index in indices.values()):
            groups = {name: set(frame.iloc[index].subject_id) for name, index in indices.items()}
            if any(groups[a] & groups[b] for a, b in (("train", "validation"), ("train", "test"),
                                                      ("validation", "test"))):
                raise ValueError("Subject leakage")
            return indices, split_seed
    raise ValueError("Cannot construct disjoint subject splits containing both classes")


def score_model(estimator, values, kind):
    if list(estimator.classes_) != [0, 1]:
        raise ValueError("Expected classifier classes [0, 1]")
    if kind == "rf":
        return estimator.predict_proba(values)[:, 1]
    if kind == "svm":
        return estimator.decision_function(values)
    raise ValueError("Unknown classifier kind")


def metrics(labels, predictions):
    report = classification_report(labels, predictions, labels=[0, 1],
                                   target_names=["ALERT", "DROWSY"], output_dict=True, zero_division=0)
    return {"accuracy": float(accuracy_score(labels, predictions)),
            "macro_f1": float(f1_score(labels, predictions, labels=[0, 1], average="macro", zero_division=0)),
            "per_class": {name: report[name] for name in ("ALERT", "DROWSY")},
            "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
            "matrix_order": ["ALERT", "DROWSY"], "windows": len(labels)}


def rank(result):
    return (result["macro_f1"], result["per_class"]["DROWSY"]["recall"],
            result["per_class"]["DROWSY"]["precision"])


def candidates(seed):
    for depth in (6, None):
        yield "rf", {"max_depth": depth, "min_samples_leaf": 3}, RandomForestClassifier(
            n_estimators=150, max_depth=depth, min_samples_leaf=3, class_weight="balanced",
            random_state=seed, n_jobs=1), (0.35, 0.5, 0.65)
    for c in (0.1, 1.0, 10.0):
        yield "svm", {"C": c, "kernel": "rbf", "gamma": "scale"}, make_pipeline(
            StandardScaler(), SVC(C=c, gamma="scale", class_weight="balanced")), (-0.5, 0.0, 0.5)


def train(features, output_dir, seed=42):
    command_start = time.perf_counter()
    frame, extraction = load_features(features)
    quality = {"source_videos": len(extraction["videos"]),
               "source_subjects": len({v["subject_id"] for v in extraction["videos"]}),
               "accepted_feature_windows": len(frame),
               "duplicate_pts_frames_skipped": sum(v.get("duplicate_pts_skipped", 0) for v in extraction["videos"]),
               "by_class": {}}
    for name in ("ALERT", "DROWSY"):
        videos = [v for v in extraction["videos"] if v["label"] == name]
        accepted = sum(v["accepted_windows"] for v in videos)
        rejected = sum(v.get("rejected_windows", 0) for v in videos)
        attempted = sum(v.get("candidate_windows", v["accepted_windows"] + v.get("rejected_windows", 0))
                        for v in videos)
        quality["by_class"][name] = {"videos": len(videos), "candidate_windows": attempted,
                                     "accepted_windows": accepted, "rejected_windows": rejected,
                                     "acceptance_rate": accepted / attempted if attempted else None,
                                     "videos_with_no_accepted_windows": sum(v["accepted_windows"] == 0 for v in videos)}
    # Use exactly the same valid endpoints for rule / RF / SVM comparison.
    unknown_baseline = int((frame.baseline_prediction == -1).sum())
    frame = frame[frame.baseline_prediction != -1].reset_index(drop=True)
    indices, split_seed = split_subjects(frame, seed)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError("Run directory exists; choose a new one to preserve held-out results")
    output_dir.mkdir(parents=True)
    x = frame[list(FEATURE_NAMES)].to_numpy(dtype=float)
    y = frame.label.to_numpy(dtype=int)
    train_idx, val_idx, test_idx = (indices[k] for k in ("train", "validation", "test"))
    best, trials, total_fit_seconds = {}, [], 0.0
    for kind, parameters, estimator, thresholds in candidates(seed):
        fit_start = time.perf_counter()
        estimator.fit(x[train_idx], y[train_idx])
        fit_seconds = time.perf_counter() - fit_start
        total_fit_seconds += fit_seconds
        scores = score_model(estimator, x[val_idx], kind)
        for threshold in thresholds:
            result = metrics(y[val_idx], (scores >= threshold).astype(int))
            trial = {"kind": kind, "parameters": parameters, "threshold": threshold,
                     "fit_seconds": fit_seconds, "validation": result}
            trials.append(trial)
            if kind not in best or rank(result) > rank(best[kind]["validation"]):
                best[kind] = {**trial, "estimator": estimator}
    selected_kind = max(best, key=lambda kind: rank(best[kind]["validation"]))
    # Freeze selection before looking at test labels or scores.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    versions = {"python": platform.python_version(), "sklearn": sklearn.__version__,
                "numpy": np.__version__, "joblib": joblib.__version__}
    split_manifest = {name: {"subjects": sorted(set(frame.iloc[index].subject_id)),
                            "videos": sorted(set(frame.iloc[index].video_id)),
                            "windows": len(index),
                            "class_counts": {str(k): int((y[index] == k).sum()) for k in (0, 1)}}
                      for name, index in indices.items()}
    feature_hash = sha256_file(features)
    results, predictions = {}, frame.iloc[test_idx][["subject_id", "video_id", "end_s", "label"]].copy()
    for kind, candidate in best.items():
        estimator = candidate["estimator"]
        scores = score_model(estimator, x[test_idx], kind)
        predicted = (scores >= candidate["threshold"]).astype(int)
        # Per-window estimator latency only; excludes MediaPipe/camera/network.
        latencies = []
        for row in x[test_idx][:200]:
            start = time.perf_counter()
            score_model(estimator, row.reshape(1, -1), kind)
            latencies.append((time.perf_counter() - start) * 1000)
        provenance = {"features": feature_hash, "seed": seed, "split": split_manifest,
                      "kind": kind, "parameters": candidate["parameters"],
                      "threshold": candidate["threshold"], "versions": versions}
        model_hash = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()[:8]
        version = f"{kind}-uta-{stamp[:8]}-{model_hash}"
        artifact = {"format": ARTIFACT_FORMAT, "kind": kind, "model_version": version,
                    "feature_version": FEATURE_VERSION, "feature_names": list(FEATURE_NAMES),
                    "feature_config": extraction["feature_config"], "estimator": estimator,
                    "threshold": candidate["threshold"], "versions": versions,
                    "landmarker_sha256": extraction["landmarker_sha256"],
                    "mediapipe_version": extraction["mediapipe_version"],
                    "features_sha256": feature_hash, "split": split_manifest,
                    "label_mapping": {"ALERT": 0, "DROWSY": 1},
                    "score_kind": "uncalibrated vote fraction" if kind == "rf" else "decision margin",
                    "trained_at_utc": stamp}
        joblib.dump(artifact, output_dir / f"{kind}.joblib")
        if kind == selected_kind:
            joblib.dump(artifact, output_dir / "selected.joblib")
        results[kind] = {k: v for k, v in candidate.items() if k != "estimator"}
        results[kind].update({"test": metrics(y[test_idx], predicted), "model_version": version,
                             "latency_estimator_ms": {"median": float(np.median(latencies)),
                                                      "p95": float(np.percentile(latencies, 95))}})
        predictions[f"{kind}_score"] = scores
        predictions[f"{kind}_prediction"] = predicted
    baseline_val = metrics(y[val_idx], frame.iloc[val_idx].baseline_prediction.to_numpy())
    baseline_test = metrics(y[test_idx], frame.iloc[test_idx].baseline_prediction.to_numpy())
    predictions["baseline_prediction"] = frame.iloc[test_idx].baseline_prediction.to_numpy()
    predictions.to_csv(output_dir / "test_predictions.csv", index=False)
    per_subject = {}
    for subject, rows in predictions.groupby("subject_id"):
        per_subject[str(subject)] = {name: metrics(rows.label.to_numpy(), rows[f"{name}_prediction"].to_numpy())
                                    for name in ("baseline", "rf", "svm")}
    report = {"created_at_utc": stamp, "features_sha256": feature_hash,
              "feature_version": FEATURE_VERSION, "feature_config": extraction["feature_config"],
              "versions": versions, "seed": seed, "split_seed": split_seed, "split": split_manifest,
              "excluded_baseline_warmup_windows": unknown_baseline, "data_quality": quality,
              "validation_trials": trials, "models": results,
              "baseline": {"validation": baseline_val, "test": baseline_test},
              "per_subject_test": per_subject,
              "selected_kind": selected_kind,
              "timing_seconds": {"total_estimator_fit": total_fit_seconds,
                                 "train_and_evaluate_command": time.perf_counter() - command_start},
              "deployment_recommendation": "review_ml_on_camera" if rank(best[selected_kind]["validation"])
                  > rank(baseline_val) else "keep_baseline_until_better_validation",
              "limitations": ["Pilot subject holdout, not the official 5-fold UTA protocol",
                  "Weak video-level labels; no frame-level onset/detection-delay claim",
                  "Binary drowsiness candidate only; DISTRACTED and event confirmation require camera tests",
                  "Scores are not calibrated confidence or probabilities of real-world correctness",
                  "Overlapping test windows are correlated; window count is not independent sample count",
                  "No deployment safety or accuracy claim from this experiment"]}
    write_json(output_dir / "report.json", report)
    write_json(output_dir / "split.json", split_manifest)
    write_json(output_dir / "extraction.json", extraction)
    locked = sorted({f"{d.metadata['Name']}=={d.version}" for d in distributions()
                     if d.metadata.get("Name")})
    (output_dir / "requirements-lock.txt").write_text("\n".join(locked) + "\n", encoding="utf-8")
    lines = ["# Binary drowsiness experiment", "", "Generated from actual input feature rows.", "",
             "| Method | Validation macro F1 | Test macro F1 | Drowsy recall | Drowsy precision |",
             "|---|---:|---:|---:|---:|"]
    for name, val, test in [("baseline", baseline_val, baseline_test),
                            *((kind, result["validation"], result["test"]) for kind, result in results.items())]:
        lines.append(f"| {name} | {val['macro_f1']:.4f} | {test['macro_f1']:.4f} | "
                     f"{test['per_class']['DROWSY']['recall']:.4f} | "
                     f"{test['per_class']['DROWSY']['precision']:.4f} |")
        write_json(output_dir / f"confusion_{name}.json", {"order": ["ALERT", "DROWSY"],
                                                         "rows_true_columns_predicted": test["confusion_matrix"]})
    lines += ["", f"Selected on validation: {selected_kind}.", "",
              f"Input: {quality['source_subjects']} people / {quality['source_videos']} videos; "
              f"{quality['accepted_feature_windows']} valid feature windows.",
              f"Baseline warmup endpoints excluded from all comparisons: {unknown_baseline}.", "",
              *[f"- {note}" for note in report["limitations"]]]
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Selected {selected_kind} on validation. Review {output_dir / 'comparison.md'}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        train(args.features, args.output_dir, args.seed)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
