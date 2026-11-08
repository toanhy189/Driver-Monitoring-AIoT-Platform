"""Grouped development search; freeze selection before the historical test audit.

The previous test is reused only as a regression audit, never a new independent
benchmark. Group-CV scores are tuning scores, not an unbiased nested-CV estimate.
"""

import argparse
from dataclasses import asdict
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
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from ml.dataset import sha256_file
from ml.extract import write_json
from ml.features import FEATURE_GROUPS, FEATURE_VERSION
from ml.train import ARTIFACT_FORMAT, load_features, metrics, score_model


def candidates(seed=42):
    for depth in (6, None):
        for leaf in (3, 15):
            for features in ("sqrt", .8):
                parameters = {"max_depth": depth, "min_samples_leaf": leaf,
                              "max_features": features, "n_estimators": 150}
                yield "rf", parameters, RandomForestClassifier(**parameters, class_weight="balanced",
                                                               random_state=seed, n_jobs=1)
    for c in (.1, 1., 10.):
        for gamma in ("scale", .1):
            parameters = {"C": c, "gamma": gamma, "kernel": "rbf"}
            yield "svm", parameters, make_pipeline(StandardScaler(), SVC(**parameters, class_weight="balanced"))


def thin_training_rows(frame, separation):
    """Use non-overlapping training windows; validate on every admitted endpoint."""
    retained = []
    for _, rows in frame.groupby("video_id", sort=True):
        last = -float("inf")
        for index, end in rows.sort_values("end_s").end_s.items():
            if end - last >= separation - 1e-8:
                retained.append(index)
                last = end
    return np.asarray(retained, dtype=int)


def grouped_folds(frame, development_subjects, test_subjects, n_splits=4, seed=42):
    development, test = set(development_subjects), set(test_subjects)
    if development & test or development | test != set(frame.subject_id):
        raise ValueError("Explicit development/test subjects must be disjoint and cover all people")
    dev = frame[frame.subject_id.isin(development)].reset_index(drop=True)
    splitter = GroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = []
    for train_idx, val_idx in splitter.split(dev, dev.label, groups=dev.subject_id):
        train_people, val_people = set(dev.iloc[train_idx].subject_id), set(dev.iloc[val_idx].subject_id)
        if train_people & val_people or (train_people | val_people) & test:
            raise ValueError("Subject leakage")
        if any(set(dev.iloc[idx].label) != {0, 1} for idx in (train_idx, val_idx)):
            raise ValueError("Every fold needs both video labels")
        folds.append((train_idx, val_idx))
    return dev, folds


def person_summary(labels, predicted, people):
    """Every person gets equal weight, regardless of source video length."""
    values = []
    for person in sorted(set(people)):
        selected = people == person
        y, p = labels[selected], predicted[selected]
        tn, fp, fn, tp = np.bincount(y * 2 + p, minlength=4).astype(float)
        recall = tp / max(tp + fn, 1)
        precision = tp / max(tp + fp, 1)
        fpr = fp / max(tn + fp, 1)
        f1_pos = 2 * tp / max(2 * tp + fp + fn, 1)
        f1_neg = 2 * tn / max(2 * tn + fp + fn, 1)
        values.append(((f1_pos + f1_neg) / 2, recall, precision, fpr,
                       (tp + tn) / max(tn + fp + fn + tp, 1)))
    values = np.asarray(values)
    return {"macro_f1": float(values[:, 0].mean()), "std_person_macro_f1": float(values[:, 0].std()),
            "drowsy_recall": float(values[:, 1].mean()), "drowsy_precision": float(values[:, 2].mean()),
            "false_positive_rate": float(values[:, 3].mean()), "accuracy": float(values[:, 4].mean())}


def selection_rank(summary, recall_target=.75, fpr_limit=.30):
    # Experimental targets are stated before training, not a certified policy.
    violation = max(0., recall_target - summary["drowsy_recall"]) + max(0., summary["false_positive_rate"] - fpr_limit)
    return (violation < 1e-12, -violation, summary["macro_f1"],
            -summary["std_person_macro_f1"], summary["drowsy_recall"])


def optimize(feature_paths, split_plan, output_dir, seed=42, n_splits=4,
             recall_target=.75, fpr_limit=.30, candidate_specs=None):
    started = time.perf_counter()
    output_dir = Path(output_dir)
    if (output_dir / "report.json").exists() or (output_dir / "selection-frozen.json").exists():
        raise ValueError("Finished/frozen run exists; preserve its selection and audit")
    split = json.loads(Path(split_plan).read_text(encoding="utf-8"))["planned_subject_split"]
    development_subjects = sorted(set(split["train"]) | set(split["validation"]))
    test_subjects = sorted(split["test"])
    loaded, endpoints = {}, None
    for path in feature_paths:
        frame, audit = load_features(path)
        keys = frame[["subject_id", "video_id", "end_s", "label"]].reset_index(drop=True)
        if endpoints is not None and not keys.equals(endpoints):
            raise ValueError("All window experiments must use identical people/labels/endpoints")
        endpoints = keys
        seconds = audit["feature_config"]["window_seconds"]
        if seconds in loaded:
            raise ValueError("Duplicate window length")
        loaded[seconds] = (frame, audit, Path(path))
    specs = list(candidates(seed) if candidate_specs is None else candidate_specs)
    versions = {"python": platform.python_version(), "sklearn": sklearn.__version__,
                "numpy": np.__version__, "joblib": joblib.__version__}
    plan = {"feature_version": FEATURE_VERSION, "feature_sha256": {str(s): sha256_file(p) for s, (_, _, p) in loaded.items()},
        "development_subjects": development_subjects, "historical_test_subjects": test_subjects,
        "feature_groups": {k: list(v) for k, v in FEATURE_GROUPS.items()},
        "seed": seed, "cv_folds": n_splits, "versions": versions,
        "parameters": [{"kind": kind, **parameters} for kind, parameters, _ in specs],
        "rf_thresholds": [float(v) for v in np.linspace(.25, .75, 11)],
        "svm_thresholds": [float(v) for v in np.linspace(-1., 1., 9)],
        "objective": {"experimental_mean_person_drowsy_recall_target": recall_target,
                      "experimental_mean_person_false_positive_rate_limit": fpr_limit,
                      "rank": "feasible, minimum constraint violation, mean person macro F1, lower person F1 SD, recall"},
        "training_thinning": "greedy non-overlapping windows within each source video",
        "limits": ["Historical test already inspected: regression audit only; new people needed for final evaluation",
                   "Grouped CV used for tuning, not an unbiased nested-CV performance estimate",
                   "Original weak video labels retained; no frame-level or event-onset claims",
                   "Validation/test windows overlap and are correlated; window counts are not independent sample counts",
                   "All window variants share the 20s quality gate; invalid periods are excluded",
                   "Eye closures sampled at <=10Hz; short blinks can be missed",
                   "Recall/FPR targets are experimental defaults, not group-approved operating policy"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "optimization-plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Resume plan differs; create a new run directory")
    write_json(plan_path, plan)
    cache_dir = output_dir / "cv-cache"
    cache_dir.mkdir(exist_ok=True)
    trials, best, fold_manifest = [], {}, None
    for seconds, (frame, audit, feature_path) in sorted(loaded.items()):
        dev, folds = grouped_folds(frame, development_subjects, test_subjects, n_splits, seed)
        labels, people = dev.label.to_numpy(), dev.subject_id.to_numpy()
        current_folds = [{"train_subjects": sorted(set(dev.iloc[tr].subject_id)),
                          "validation_subjects": sorted(set(dev.iloc[va].subject_id))} for tr, va in folds]
        if fold_manifest is not None and current_folds != fold_manifest:
            raise ValueError("Group folds changed across feature/window variants")
        fold_manifest = current_folds
        for group_name, feature_names in FEATURE_GROUPS.items():
            values = dev[list(feature_names)].to_numpy(dtype=float)
            for kind, parameters, template in specs:
                identity = {"window_seconds": seconds, "feature_group": group_name, "kind": kind,
                            "parameters": parameters, "plan": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()}
                key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
                cached = cache_dir / f"{key}.npz"
                if cached.exists():
                    with np.load(cached) as saved:
                        scores = saved["scores"]
                    if len(scores) != len(dev) or not np.isfinite(scores).all():
                        raise ValueError("Invalid CV score cache")
                else:
                    scores = np.full(len(dev), np.nan)
                    for train_idx, val_idx in folds:
                        retained = thin_training_rows(dev.iloc[train_idx], seconds)
                        estimator = clone(template)
                        estimator.fit(values[retained], labels[retained])
                        scores[val_idx] = score_model(estimator, values[val_idx], kind)
                    if not np.isfinite(scores).all():
                        raise ValueError("Missing out-of-fold predictions")
                    np.savez_compressed(cached, scores=scores)
                thresholds = plan["rf_thresholds" if kind == "rf" else "svm_thresholds"]
                for threshold in thresholds:
                    predicted = (scores >= threshold).astype(int)
                    summary = person_summary(labels, predicted, people)
                    fold_scores = [person_summary(labels[va], predicted[va], people[va]) for _, va in folds]
                    trial = {**{k: v for k, v in identity.items() if k != "plan"},
                             "threshold": threshold, "cv_mean_person": summary,
                             "cv_folds": fold_scores, "oof_cache": cached.name}
                    trials.append(trial)
                    if kind not in best or selection_rank(summary, recall_target, fpr_limit) > selection_rank(best[kind]["cv_mean_person"], recall_target, fpr_limit):
                        best[kind] = trial
                print(f"CV window={seconds:g}s group={group_name} {kind} {parameters}; candidates={len(trials)}", flush=True)
                write_json(output_dir / "cv-progress.json", {"completed_threshold_trials": len(trials), "best": best})
    selected_kind = max(best, key=lambda k: selection_rank(best[k]["cv_mean_person"], recall_target, fpr_limit))
    write_json(output_dir / "selection-frozen.json", {"selected_kind": selected_kind, "best": best,
               "selected_before_historical_test_predictions": True, "folds": fold_manifest})
    write_json(output_dir / "cv-trials.json", trials)
    flat_trials = [{"window_seconds": t["window_seconds"], "feature_group": t["feature_group"],
                    "kind": t["kind"], "parameters": json.dumps(t["parameters"], sort_keys=True),
                    "threshold": t["threshold"], **t["cv_mean_person"]} for t in trials]
    pd.DataFrame(flat_trials).to_csv(output_dir / "cv-trials.csv", index=False)
    ablations = []
    for seconds in loaded:
        for group in FEATURE_GROUPS:
            for kind in ("rf", "svm"):
                choices = [t for t in trials if t["window_seconds"] == seconds
                           and t["feature_group"] == group and t["kind"] == kind]
                if choices:
                    winner = max(choices, key=lambda t: selection_rank(t["cv_mean_person"], recall_target, fpr_limit))
                    ablations.append({"window_seconds": seconds, "feature_group": group, "kind": kind,
                                      "threshold": winner["threshold"], **winner["cv_mean_person"]})
    pd.DataFrame(ablations).to_csv(output_dir / "ablation-summary.csv", index=False)
    # Only here start fitting the chosen development models / reporting historical test scores.
    models, final_artifacts = {}, {}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reference_frame = loaded[min(loaded)][0]
    test_frame = reference_frame[reference_frame.subject_id.isin(test_subjects)]
    predictions = test_frame[["subject_id", "video_id", "end_s", "label"]].copy().reset_index(drop=True)
    predictions["baseline_prediction"] = test_frame.baseline_prediction.to_numpy()
    for kind, choice in best.items():
        frame, extraction, feature_path = loaded[choice["window_seconds"]]
        dev = frame[frame.subject_id.isin(development_subjects)].reset_index(drop=True)
        test = frame[frame.subject_id.isin(test_subjects)]
        names = FEATURE_GROUPS[choice["feature_group"]]
        retained = thin_training_rows(dev, choice["window_seconds"])
        template = next(t for k, p, t in specs if k == kind and p == choice["parameters"])
        estimator = clone(template).fit(dev.iloc[retained][list(names)].to_numpy(dtype=float), dev.iloc[retained].label.to_numpy())
        scores = score_model(estimator, test[list(names)].to_numpy(dtype=float), kind)
        predicted = (scores >= choice["threshold"]).astype(int)
        version_hash = hashlib.sha256(json.dumps({"plan": plan, "choice": choice}, sort_keys=True).encode()).hexdigest()[:8]
        version = f"{kind}-uta-v2-{stamp[:8]}-{version_hash}"
        artifact = {"format": ARTIFACT_FORMAT, "kind": kind, "model_version": version,
            "feature_version": FEATURE_VERSION, "feature_names": list(names),
            "feature_config": extraction["feature_config"], "estimator": estimator,
            "threshold": choice["threshold"], "versions": versions,
            "landmarker_sha256": extraction["landmarker_sha256"], "mediapipe_version": extraction["mediapipe_version"],
            "features_sha256": sha256_file(feature_path), "split": {"development": development_subjects, "historical_test": test_subjects},
            "label_mapping": {"ALERT": 0, "DROWSY": 1},
            "score_kind": "uncalibrated vote fraction" if kind == "rf" else "decision margin", "trained_at_utc": stamp}
        joblib.dump(artifact, output_dir / f"{kind}.joblib")
        if kind == selected_kind:
            joblib.dump(artifact, output_dir / "selected.joblib")
        final_artifacts[kind] = artifact
        models[kind] = {**choice, "model_version": version, "training_windows_after_thinning": len(retained),
            "test": metrics(test.label.to_numpy(), predicted),
            "test_mean_person": person_summary(test.label.to_numpy(), predicted, test.subject_id.to_numpy())}
        predictions[f"{kind}_score"], predictions[f"{kind}_prediction"] = scores, predicted
    baseline_test = metrics(predictions.label.to_numpy(), predictions.baseline_prediction.to_numpy())
    dev_ref = reference_frame[reference_frame.subject_id.isin(development_subjects)]
    baseline_cv = person_summary(dev_ref.label.to_numpy(), dev_ref.baseline_prediction.to_numpy(), dev_ref.subject_id.to_numpy())
    predictions.to_csv(output_dir / "test_predictions.csv", index=False)
    selected = final_artifacts[selected_kind]
    from ml.runtime import DrowsinessModel
    runtime = DrowsinessModel(output_dir / "selected.joblib")
    selected_test = loaded[best[selected_kind]["window_seconds"]][0]
    selected_test = selected_test[selected_test.subject_id.isin(test_subjects)]
    restored = score_model(runtime.estimator, selected_test[runtime.feature_names].to_numpy(dtype=float), runtime.kind)
    np.testing.assert_allclose(restored, predictions[f"{selected_kind}_score"], rtol=1e-12, atol=1e-12)
    report = {"created_at_utc": stamp, "feature_version": FEATURE_VERSION, "versions": versions,
        "selected_kind": selected_kind, "models": models, "baseline": {"test": baseline_test, "cv_mean_person": baseline_cv},
        "development_subjects": development_subjects, "historical_test_subjects": test_subjects,
        "cv_group_folds": fold_manifest, "selection_policy": plan["objective"], "limitations": plan["limits"],
        "source_subjects": int(reference_frame.subject_id.nunique()), "source_videos": int(reference_frame.video_id.nunique()),
        "common_windows": len(reference_frame), "historical_test_windows": len(predictions),
        "selected_feature_config": selected["feature_config"], "selected_feature_names": selected["feature_names"],
        "selected_cv_targets_met": bool(selection_rank(best[selected_kind]["cv_mean_person"], recall_target, fpr_limit)[0]),
        "threshold_trials": len(trials),
        "training_seconds": time.perf_counter() - started, "reload_check_matching_predictions": len(restored),
        "per_subject_test": {str(person): {k: metrics(rows.label.to_numpy(), rows[f"{k}_prediction"].to_numpy())
                             for k in ("baseline", "rf", "svm")} for person, rows in predictions.groupby("subject_id")}}
    write_json(output_dir / "report.json", report)
    for name, result in {"baseline": report["baseline"], **models}.items():
        write_json(output_dir / f"confusion_{name}.json", {"order": ["ALERT", "DROWSY"],
            "rows_true_columns_predicted": result["test"]["confusion_matrix"]})
    lines = ["# Optimized binary drowsiness experiment", "", "Selection: 4-fold GroupKFold on development people only.",
        "Historical test below was previously inspected: regression audit, not a fresh independent benchmark.", "",
        "| Method | Group-CV mean-person F1 | Historical test accuracy | Test macro F1 | DROWSY recall | DROWSY precision |",
        "|---|---:|---:|---:|---:|---:|"]
    for name, result in {"baseline": report["baseline"], **models}.items():
        cv = result["cv_mean_person"]
        test = result["test"]
        lines.append(f"| {name} | {cv['macro_f1']:.4f} | {test['accuracy']:.4f} | {test['macro_f1']:.4f} | "
                     f"{test['per_class']['DROWSY']['recall']:.4f} | {test['per_class']['DROWSY']['precision']:.4f} |")
    lines += ["", f"Selected from grouped development CV: **{selected_kind}**.",
        f"Selected model version: `{selected['model_version']}`.",
        f"Selected window: {selected['feature_config']['window_seconds']:g}s; features: {best[selected_kind]['feature_group']}.",
        f"Selected uncalibrated score cutoff: {selected['threshold']:g}.",
        f"Experimental CV targets: mean-person DROWSY recall >= {recall_target:.2f}, FPR <= {fpr_limit:.2f}; "
        f"targets satisfied: {report['selected_cv_targets_met']}.",
        f"Selected CV mean-person recall: {best[selected_kind]['cv_mean_person']['drowsy_recall']:.4f}; "
        f"FPR: {best[selected_kind]['cv_mean_person']['false_positive_rate']:.4f}.",
        f"Historical test audit: {len(predictions)} common valid windows / {len(test_subjects)} people.", "",
        "## Changes", "", "- Pixel geometry shared by offline extraction and live inference.",
        "- 19 causal temporal features; core / eyes / full ablations, 5/10/20s windows.",
        "- Non-overlapping training windows; equal-person grouped CV selection.",
        "- RF/SVM hyperparameters and thresholds chosen without historical test predictions.",
        "- Baseline here uses corrected geometry; old v1 run remains unchanged.", "", "## Limits", "",
        *[f"- {note}" for note in plan["limits"]], "",
        f"Reloaded artifact: all {len(restored)} saved predictions match; camera not opened."]
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "requirements-lock.txt").write_text("\n".join(sorted({f"{d.metadata['Name']}=={d.version}"
        for d in distributions() if d.metadata.get("Name")})) + "\n", encoding="utf-8")
    print(f"Selected {selected_kind}: {selected['model_version']}; report={output_dir / 'report.json'}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, nargs="+", required=True)
    parser.add_argument("--split-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    optimize(args.features, args.split_plan, args.output_dir)


if __name__ == "__main__":
    main()
