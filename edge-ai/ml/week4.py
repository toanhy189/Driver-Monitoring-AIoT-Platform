"""Reuse frozen results; prepare independently reviewed three-state labels."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.dataset import sha256_file
from ml.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig
from ml.nthu import write_json
from ml.train import metrics

STATES = {"ATTENTIVE": 0, "DISTRACTED": 1, "DROWSY": 2}


def compare_rules(features, predictions, output):
    """No inference/refit. Evaluate all methods on identical admitted windows."""
    keys = ["subject_id", "video_id", "end_s"]
    data = pd.read_csv(features)
    predicted = pd.read_csv(predictions)
    if data.duplicated(keys).any() or predicted.duplicated(keys).any():
        raise ValueError("Duplicate window identity")
    rows = data.merge(predicted[keys+["rf_prediction", "svm_prediction"]], on=keys, validate="one_to_one")
    if len(rows) != len(data) or len(rows) != len(predicted):
        raise ValueError("Feature/OOF coverage mismatch")
    admitted = rows.baseline_prediction.isin([0, 1])
    report = {"features_sha256": sha256_file(features), "oof_sha256": sha256_file(predictions),
              "evaluation": "development OOF, already used for model selection",
              "windows": len(rows), "baseline_coverage": float(admitted.mean()),
              "baseline_abstentions": int((~admitted).sum()), "common_windows": int(admitted.sum()),
              "models_on_common_windows": {}}
    for name, column in (("rules", "baseline_prediction"), ("rf", "rf_prediction"), ("svm", "svm_prediction")):
        report["models_on_common_windows"][name] = metrics(rows.loc[admitted, "label"].to_numpy(),
                                                               rows.loc[admitted, column].to_numpy()) if admitted.any() else None
    report["limits"] = ["Admitted windows only; rejected/ambiguous windows are not evaluated.",
        "Window FPR is not false-warning episodes/hour; no onset delay is inferred from filtered windows.",
        "Binary drowsy/not-drowsy labels do not evaluate distraction."]
    write_json(output, report)
    return report


def prepare_states(features, annotations, output):
    configurations = []
    for path in features:
        audit = json.loads((Path(path).parent/"extraction.json").read_text())
        if audit.get("feature_version") != FEATURE_VERSION or audit.get("features_sha256") != sha256_file(path):
            raise ValueError("Feature CSV does not match its extraction audit")
        configurations.append(audit["feature_config"])
    if any(config != configurations[0] for config in configurations):
        raise ValueError("Cannot mix different temporal window configurations")
    tables = [pd.read_csv(path, dtype={"subject_id": str, "video_id": str}) for path in features]
    rows = pd.concat(tables, ignore_index=True)
    labels = pd.read_csv(annotations, keep_default_na=False, dtype={"subject_id": str, "video_id": str})
    required = {"subject_id", "video_id", "video_sha256", "start_s", "end_s", "state",
                "reviewer", "source", "label_method", "split"}
    if not required <= set(labels.columns) or not len(labels):
        raise ValueError("Independent interval annotations are required; see the template")
    if set(labels.state) != set(STATES):
        raise ValueError("All three independently labelled states are required; binary labels are insufficient")
    if not labels.split.isin(["train", "validation", "test"]).all():
        raise ValueError("Explicit train/validation/test split required")
    if labels.groupby("subject_id").split.nunique().max() != 1:
        raise ValueError("A person appears in multiple splits")
    if labels.groupby("video_sha256").split.nunique().max() != 1:
        raise ValueError("Same video content appears in multiple splits")
    if not labels.label_method.isin(["manual_review", "dataset_original"]).all():
        raise ValueError("Labels cannot be derived from model/rule predictions")
    for column in ("reviewer", "source", "video_sha256"):
        if labels[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Missing label provenance: {column}")
    labels["start_s"] = pd.to_numeric(labels.start_s)
    labels["end_s"] = pd.to_numeric(labels.end_s)
    if not np.isfinite(labels[["start_s", "end_s"]].to_numpy()).all() or (
            (labels.start_s < 0) | (labels.end_s <= labels.start_s)).any():
        raise ValueError("Invalid annotation interval")
    if rows.duplicated(["subject_id", "video_id", "end_s"]).any():
        raise ValueError("Duplicate feature windows")
    selected = []
    for (_, _), intervals in labels.groupby(["subject_id", "video_id"]):
        intervals = intervals.sort_values("start_s")
        if any(b < a for a, b in zip(intervals.end_s.iloc[:-1], intervals.start_s.iloc[1:])):
            raise ValueError("Overlapping annotation intervals")
        for interval in intervals.itertuples():
            subset = rows[(rows.subject_id == interval.subject_id) & (rows.video_id == interval.video_id)
                          & (rows.video_sha256 == interval.video_sha256)
                          & (rows.start_s >= interval.start_s) & (rows.end_s <= interval.end_s)].copy()
            subset["state"] = interval.state
            subset["label"] = STATES[interval.state]
            subset["split"] = interval.split
            subset["reviewer"] = interval.reviewer
            subset["label_source"] = interval.source
            selected.append(subset)
    result = pd.concat(selected, ignore_index=True)
    if not len(result) or result.duplicated(["subject_id", "video_id", "end_s"]).any():
        raise ValueError("No eligible windows or ambiguous interval assignment")
    if not np.isfinite(result[list(FEATURE_NAMES)].to_numpy()).all():
        raise ValueError("Non-finite features")
    for split in ("train", "validation", "test"):
        if set(result.loc[result.split == split, "state"]) != set(STATES):
            raise ValueError(f"All three classes required in {split}; collect/review more data")
    output = Path(output)
    if output.exists():
        raise ValueError("Preserve existing labelled dataset; choose a new output")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    write_json(output.with_suffix(".audit.json"), {"feature_version": FEATURE_VERSION,
        "feature_config": configurations[0], "annotation_sha256": sha256_file(annotations),
        "input_sha256": {str(p): sha256_file(p) for p in features}, "output_sha256": sha256_file(output),
        "windows": len(result), "counts": result.groupby(["split", "state"]).size().rename("windows").reset_index().to_dict("records"),
        "note": "Existing reviewed feature windows only; no invented labels or new face extraction."})
    return result


def train_states(features, output):
    """Fit RF/SVM on reviewed data; select only with validation, then evaluate test once."""
    import joblib
    import mediapipe as mp
    import sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
    from config import TASK_PATH

    output = Path(output)
    if output.exists():
        raise ValueError("Training output already exists; preserve frozen results")
    audit = json.loads(Path(features).with_suffix(".audit.json").read_text())
    if audit["output_sha256"] != sha256_file(features) or audit["feature_version"] != FEATURE_VERSION:
        raise ValueError("Reviewed dataset/schema changed")
    rows = pd.read_csv(features)
    if rows.groupby("subject_id").split.nunique().max() != 1:
        raise ValueError("Person leakage")
    # Windows overlap. Fit on non-overlapping windows within each source video.
    fit_rows = []
    for _, video in rows[rows.split == "train"].groupby("video_id"):
        end = -float("inf")
        for index, row in video.sort_values("end_s").iterrows():
            if row.start_s >= end-1e-8:
                fit_rows.append(index)
                end = row.end_s
    train = rows.loc[fit_rows]
    validation = rows[rows.split == "validation"]
    if set(train.label) != {0, 1, 2}:
        raise ValueError("Non-overlapping train windows lack a class")
    names = list(FEATURE_NAMES)
    estimators = {"rf": RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5,
                    class_weight="balanced", random_state=42, n_jobs=2),
                  "svm": make_pipeline(StandardScaler(), SVC(C=1, gamma="scale", class_weight="balanced"))}
    validation_scores = {}
    for kind, estimator in estimators.items():
        estimator.fit(train[names].to_numpy(), train.label.to_numpy())
        validation_scores[kind] = float(f1_score(validation.label,
            estimator.predict(validation[names].to_numpy()), average="macro", labels=[0,1,2], zero_division=0))
    selected = max(estimators, key=lambda key: (validation_scores[key], key == "rf"))
    output.mkdir(parents=True)
    write_json(output/"selection-frozen.json", {"features_sha256": sha256_file(features),
        "selected_kind": selected, "validation_macro_f1": validation_scores,
        "test_used_for_selection": False, "label_mapping": STATES})
    test = rows[rows.split == "test"]
    report = {"evaluation": "person-disjoint supplied test; freshness must be verified from dataset history",
              "selected_kind": selected, "fit_windows": len(train), "test_windows": len(test), "models": {}}
    for kind, estimator in estimators.items():
        predicted = estimator.predict(test[names].to_numpy())
        report["models"][kind] = {"accuracy": float(accuracy_score(test.label, predicted)),
            "confusion_matrix": confusion_matrix(test.label, predicted, labels=[0,1,2]).tolist(),
            "classification_report": classification_report(test.label, predicted, labels=[0,1,2],
                target_names=list(STATES), output_dict=True, zero_division=0)}
        artifact = {"format": "driver-state-v1", "feature_version": FEATURE_VERSION,
            "feature_config": audit["feature_config"], "feature_names": names, "kind": kind,
            "label_mapping": STATES, "estimator": estimator, "threshold": 0.5,
            "model_version": f"{kind}-three-state-{sha256_file(features)[:12]}",
            "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__},
            "mediapipe_version": mp.__version__, "landmarker_sha256": sha256_file(TASK_PATH)}
        joblib.dump(artifact, output/f"{kind}.joblib")
        if kind == selected:
            joblib.dump(artifact, output/"selected.joblib")
    report["limits"] = ["Do not use binary not-drowsy as ATTENTIVE or relabel low vigilance as DISTRACTED.",
                         "No physical-camera or actuator acceptance is implied by this report.",
                         "Three-state runtime-rule baseline still needs an independently labelled replay; binary baseline is insufficient."]
    write_json(output/"report.json", report)
    write_json(output/"artifact-manifest.json", {p.name: sha256_file(p) for p in output.glob("*.joblib")})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare-rules")
    compare.add_argument("--features", type=Path, required=True)
    compare.add_argument("--predictions", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    prepare = sub.add_parser("prepare-states")
    prepare.add_argument("--features", nargs="+", type=Path, required=True)
    prepare.add_argument("--annotations", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    train = sub.add_parser("train-states")
    train.add_argument("--features", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "compare-rules":
        compare_rules(args.features, args.predictions, args.output)
    elif args.command == "prepare-states":
        prepare_states(args.features, args.annotations, args.output)
    else:
        train_states(args.features, args.output)


if __name__ == "__main__":
    main()
