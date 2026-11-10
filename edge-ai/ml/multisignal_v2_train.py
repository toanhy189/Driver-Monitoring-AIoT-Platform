"""Refit RF v2 using frozen region probabilities and the original subject split.

No webcam, network, private-trial labels, or changes to the v1 bundle.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import cv2
import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier

from ml.dataset import sha256_file
from ml.multisignal_data import write_json
from ml.multisignal_features import window_label
from ml.multisignal_train import report_metrics
from ml.multisignal_v2_features import (CONFIG, DECISION_VERSION, FEATURE_NAMES, FEATURE_VERSION,
    QUALITY_VERSION, V2Window, ProbabilitySmoother, admitted_values, bundle_version, crop_quality)


def causal_rows(report, *, mask_sunglasses=False):
    window, smoother = V2Window(), ProbabilitySmoother()
    previous = None
    for row in report["samples"]:
        now = row["time_s"]
        present = bool(row.get("eyes_path") or row.get("mouth_path") or row.get("yaw") is not None)
        interrupted = not present or (previous is not None and now-previous > .5)
        previous = now
        if interrupted:
            window.reset(); smoother.reset()
            yield row, {}, None, "WARMUP"
            continue
        values = admitted_values(row, row["quality_v2"],
            mask_eyes=mask_sunglasses and report["condition"] == "sunglasses")
        values = smoother.update(now, values)
        window.add(now, values)
        yield row, values, window.snapshot(), window.last_quality_reason


def feature_rows(reports):
    result = []
    for report in reports:
        for row, values, snapshot, reason in causal_rows(report, mask_sunglasses=True):
            if snapshot is None:
                continue
            target = window_label(report["samples"], snapshot["start_s"], snapshot["end_s"])
            if target is not None:
                result.append({"x": snapshot["features"], "label": target,
                    **{key: report[key] for key in ("video_id", "subject_id", "condition", "group")}})
    return result


def enrich(source, destination):
    """Compute the same technical crop checks from the existing private crops."""
    reports = []
    destination.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(sorted(source.glob("*.json"))):
        original = json.loads(path.read_text(encoding="utf-8"))
        if original["group"] == "cnn_train":
            continue
        cached = destination/path.name
        if cached.exists():
            report = json.loads(cached.read_text(encoding="utf-8"))
            if report.get("quality_version") != QUALITY_VERSION or report.get("quality_config") != CONFIG:
                raise ValueError("Stale quality cache; use a new output directory")
        else:
            report = original
            for row in report["samples"]:
                row["quality_v2"] = {name: crop_quality(
                    cv2.imread(row[f"{name}_path"]) if row.get(f"{name}_path") else None,
                    row.get(f"{name[:-1] if name == 'eyes' else name}_sharpness"))
                    for name in ("eyes", "mouth")}
            report.update(quality_version=QUALITY_VERSION, quality_config=CONFIG)
            write_json(cached, report)
        reports.append(report)
        if (index+1) % 20 == 0:
            print(json.dumps({"quality_videos": index+1}), flush=True)
    return reports


def train(source_root, output):
    old = json.loads((source_root/"candidate/manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((source_root/"data-plan.json").read_text(encoding="utf-8"))
    if old["format"] != "driver-multisignal-v1":
        raise ValueError("Expected frozen baseline bundle")
    groups = list(plan["groups"].values())
    if any(set(a) & set(b) for i, a in enumerate(groups) for b in groups[i+1:]):
        raise ValueError("Subject overlap")
    for name, digest in old["files"].items():
        if sha256_file(source_root/"candidate"/name) != digest:
            raise ValueError("Frozen baseline changed")
    bundle = output/"candidate"
    if (bundle/"manifest.json").exists():
        raise ValueError("Never overwrite a frozen v2 candidate; select a new output")
    bundle.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(1)
    reports = enrich(source_root/"predictions"/old["files"]["regions.pt"][:12], output/"predictions")
    # Check every cached subject against the original locked plan.
    for report in reports:
        if report["group"] not in plan["groups"] or report["subject_id"] not in plan["groups"][report["group"]]:
            raise ValueError("Prediction does not belong to locked source split")
    rows = feature_rows(reports)
    fit = [r for r in rows if r["group"] == "fusion_train"]
    val = [r for r in rows if r["group"] == "validation"]
    if not fit or not val or {r["label"] for r in fit} != {0, 1}:
        raise ValueError("Missing fusion training/validation labels")
    rf = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=8,
                               class_weight="balanced", n_jobs=4, random_state=41)
    rf.fit([r["x"] for r in fit], [r["label"] for r in fit])
    actual = np.asarray([r["label"] for r in val])
    probabilities = rf.predict_proba([r["x"] for r in val])[:, 1]
    choices = []
    for enter in (.4, .5, .6, .7, .8, .9):
        predicted = (probabilities >= enter).astype(int)
        choices.append({"enter": enter, "leave": round(enter-.1, 6),
            "validation": report_metrics(actual, predicted, [0, 1]),
            "false_positive_rate": float(np.mean(predicted[actual == 0]))})
    eligible = [r for r in choices if r["false_positive_rate"] <= .1]
    selected = max(eligible or choices, key=lambda r: (r["validation"]["macro_f1"], -r["false_positive_rate"]))
    artifact = {"format": "multisignal-fusion-v2", "feature_version": FEATURE_VERSION,
        "feature_names": list(FEATURE_NAMES), "estimator": rf, "threshold": selected["enter"],
        "leave_threshold": selected["leave"], "versions": {"numpy": np.__version__, "sklearn": sklearn.__version__}}
    joblib.dump(artifact, bundle/"fusion.joblib")
    shutil.copy2(source_root/"candidate/regions.pt", bundle/"regions.pt")
    files = {name: sha256_file(bundle/name) for name in ("regions.pt", "fusion.joblib")}
    manifest = {**old, "format": "driver-multisignal-v2", "files": files,
        "feature_version": FEATURE_VERSION, "feature_names": list(FEATURE_NAMES),
        "quality_version": QUALITY_VERSION, "decision_version": DECISION_VERSION, "quality_config": CONFIG,
        "model_version": bundle_version(files, selected["enter"], selected["leave"]),
        "enter_threshold": selected["enter"], "leave_threshold": selected["leave"],
        "selected_fusion": selected, "baseline_model_version": old["model_version"],
        "trained_at": datetime.now(timezone.utc).isoformat(), "closure_profile_required": True,
        "live_diagnostic_used_for_training": False, "webcam_glasses_passed": False,
        "release_status": "EXPERIMENTAL_OFFLINE_ONLY", "physical_outputs_tested": False,
        "limitations": old["limitations"] + [
            "Technical crop checks do not establish semantic visibility behind glasses or reflections",
            "Validation has already informed earlier model selection; no valid independent final test",
            "Calibrated closure branch remains disabled until an explicit matching v3 profile is supplied",
            "No stale confidence grace; missing current observation interrupts evidence immediately"]}
    write_json(bundle/"fusion-selection.json", {"selected": selected, "candidates": choices,
        "fit_subjects": sorted({r["subject_id"] for r in fit}),
        "validation_subjects": sorted({r["subject_id"] for r in val}),
        "rows_by_group": dict(Counter(r["group"] for r in rows)),
        "frozen_before_policy_replay": True, "live_trials_used": False})
    write_json(bundle/"manifest.json", manifest)
    print(json.dumps({"status": "V2_TRAINED_EXPERIMENTAL", "model_version": manifest["model_version"],
        "selected": selected, "rows_by_group": dict(Counter(r["group"] for r in rows))}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Output must differ from the frozen baseline")
    train(args.source, args.output)
