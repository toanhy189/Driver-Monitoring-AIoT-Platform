"""Select on development people, freeze artifacts, then evaluate fresh people once."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform

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
from ml.features import FEATURE_GROUPS, FEATURE_VERSION, FeatureConfig
from ml.nthu import write_json
from ml.optimize import selection_rank, thin_training_rows
from ml.train import ARTIFACT_FORMAT, metrics, score_model


def load(path, *, expected_version=FEATURE_VERSION):
    path = Path(path)
    audit = json.loads(path.with_name("extraction.json").read_text(encoding="utf-8"))
    if (audit["feature_version"] != expected_version or audit["label_type"] != "frame_fraction"
            or audit["features_sha256"] != sha256_file(path)):
        raise ValueError("Unrecognised or changed NTHU features")
    frame = pd.read_csv(path, dtype={"subject_id": str, "video_id": str, "video_sha256": str})
    config = FeatureConfig(**audit["feature_config"])
    if frame.empty or frame.isna().any().any() or not frame.label.isin([0, 1]).all():
        raise ValueError("Empty/missing/invalid training values")
    if (not np.isfinite(frame[list(FEATURE_GROUPS["full"])].to_numpy()).all()
            or frame.duplicated(["video_id", "end_s"]).any()
            or not np.allclose(frame.end_s-frame.start_s, config.window_seconds)
            or not frame.coverage.between(config.min_coverage-1e-8, 1+1e-8).all()
            or not frame.drowsy_fraction.between(0, 1).all()
            or ((frame.label == 0) & (frame.drowsy_fraction > .2+1e-8)).any()
            or ((frame.label == 1) & (frame.drowsy_fraction < .8-1e-8)).any()):
        raise ValueError("Invalid feature geometry/label/quality")
    expected = {v["video_id"]: v for v in audit["videos"]}
    if len(frame) != audit["feature_windows"]:
        raise ValueError("Row count differs from extraction audit")
    for identifier, rows in frame.groupby("video_id"):
        entry = expected[identifier]
        if (len(rows) != entry["accepted_windows"] or set(rows.subject_id) != {entry["subject_id"]}
                or set(rows.condition) != {entry["condition"]}
                or ("video_sha256" in entry and set(rows.video_sha256) != {entry["video_sha256"]})):
            raise ValueError("Rows disagree with source audit")
    return frame, audit


def person_summary(labels, predictions, people):
    summaries, recalls, fprs = [], [], []
    for person in sorted(set(people)):
        y, p = labels[people == person], predictions[people == person]
        result = metrics(y, p)
        tn, fp, fn, tp = np.asarray(result["confusion_matrix"]).ravel()
        summaries.append((result["macro_f1"], result["accuracy"]))
        if tp+fn:
            recalls.append(float(tp/(tp+fn)))
        if tn+fp:
            fprs.append(float(fp/(tn+fp)))
    if not recalls or not fprs:
        raise ValueError("Need positive and negative people for selection")
    return {"macro_f1": float(np.mean([s[0] for s in summaries])),
            "accuracy": float(np.mean([s[1] for s in summaries])),
            "std_person_macro_f1": float(np.std([s[0] for s in summaries])),
            "drowsy_recall": float(np.mean(recalls)), "false_positive_rate": float(np.mean(fprs)),
            "people": len(summaries), "people_with_positive_labels": len(recalls),
            "people_with_negative_labels": len(fprs)}


def candidates(seed=42):
    for depth in (6, 10):
        for leaf in (5, 15, 30):
            for weight in ("balanced", {0: 1., 1: 1.}, {0: 1., 1: .75}):
                parameters = {"n_estimators": 300, "max_depth": depth, "min_samples_leaf": leaf,
                              "max_features": "sqrt", "class_weight": weight}
                yield "rf", parameters, RandomForestClassifier(**parameters, random_state=seed, n_jobs=1)
    for c in (.1, 1., 10.):
        for gamma in ("scale", .1):
            parameters = {"C": c, "gamma": gamma, "class_weight": "balanced"}
            yield "svm", parameters, make_pipeline(StandardScaler(), SVC(**parameters))


def check_people(frame, plan, role):
    expected = set(plan["development_subjects"] if role == "development" else plan["fresh_heldout_subjects"])
    opposite = set(plan["fresh_heldout_subjects"] if role == "development" else plan["development_subjects"])
    actual = set(frame.subject_id)
    if actual & opposite or not actual <= expected:
        raise ValueError("Subject leakage or unexpected person")
    if len(actual) < (8 if role == "development" else 2):
        raise ValueError("Too few valid people after audit/quality filtering")
    return sorted(expected-actual)


def select(features, plan_path, output_dir, feature_group="eyes"):
    if feature_group not in ("eyes", "full"):
        raise ValueError("NTHU selection supports eyes or full feature groups")
    frame, audit = load(features)
    if audit["role"] != "development":
        raise ValueError("Selection only accepts development features")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if plan.get("feature_version", FEATURE_VERSION) != FEATURE_VERSION:
        raise ValueError("Experiment plan uses a different feature version")
    allowed = plan.get("candidate_search_proposal", {}).get("feature_groups", ["eyes"])
    if feature_group not in allowed:
        raise ValueError("Feature group not authorised by the experiment plan")
    missing = check_people(frame, plan, "development")
    output_dir = Path(output_dir)
    if (output_dir / "selection-frozen.json").exists():
        raise ValueError("Selection already frozen; preserve it")
    output_dir.mkdir(parents=True, exist_ok=True)
    identity = {"feature_version": FEATURE_VERSION,
                "features_sha256": sha256_file(features), "plan_sha256": sha256_file(plan_path),
                "features": list(FEATURE_GROUPS[feature_group]), "seed": 42,
                "sklearn_version": sklearn.__version__, "numpy_version": np.__version__,
                "parameters": [p for _, p, _ in candidates()]}
    # Normalize integer class-weight keys for durable JSON comparisons.
    identity = json.loads(json.dumps(identity))
    identity_path = output_dir / "search-plan.json"
    if identity_path.exists() and json.loads(identity_path.read_text()) != identity:
        raise ValueError("Resume search changed; choose a new directory")
    write_json(identity_path, identity)
    labels, people = frame.label.to_numpy(), frame.subject_id.to_numpy()
    names = list(FEATURE_GROUPS[feature_group])
    x = frame[names].to_numpy(dtype=float)
    folds = list(GroupKFold(4, shuffle=True, random_state=42).split(x, labels, people))
    best, trials = {}, []
    cache_dir = output_dir / "cv-cache"
    cache_dir.mkdir(exist_ok=True)
    for index, (kind, parameters, template) in enumerate(candidates(), 1):
        key = hashlib.sha256(json.dumps({"identity": identity, "kind": kind, "parameters": parameters},
                                        sort_keys=True).encode()).hexdigest()
        cache = cache_dir / f"{key}.npz"
        if cache.exists():
            with np.load(cache) as data:
                scores = data["scores"]
        else:
            scores = np.full(len(frame), np.nan)
            for train, validation in folds:
                if set(people[train]) & set(people[validation]):
                    raise ValueError("Fold leakage")
                retained = thin_training_rows(frame.iloc[train], audit["feature_config"]["window_seconds"])
                if set(labels[retained]) != {0, 1}:
                    raise ValueError("Thinned training fold needs both labels")
                estimator = clone(template).fit(x[retained], labels[retained])
                scores[validation] = score_model(estimator, x[validation], kind)
            np.savez_compressed(cache, scores=scores)
        if len(scores) != len(frame) or not np.isfinite(scores).all():
            raise ValueError("Invalid out-of-fold predictions")
        for threshold in (np.linspace(.25, .75, 11) if kind == "rf" else np.linspace(-1, 1, 9)):
            summary = person_summary(labels, (scores >= threshold).astype(int), people)
            trial = {"kind": kind, "candidate_index": index, "parameters": parameters,
                     "threshold": float(threshold), "cv_mean_person": summary}
            trials.append(trial)
            if kind not in best or selection_rank(summary) > selection_rank(best[kind]["cv_mean_person"]):
                best[kind] = trial
        print(f"CV {index}/24 {kind}: {parameters}", flush=True)
        write_json(output_dir / "cv-progress.json", {"best": best, "trials_completed": len(trials)})
    selected_kind = max(best, key=lambda k: selection_rank(best[k]["cv_mean_person"]))
    frozen = {"selected_kind": selected_kind, "feature_group": feature_group,
              "best": best, "selection_before_heldout": not plan.get("heldout_already_inspected", False),
              "heldout_already_inspected": plan.get("heldout_already_inspected", False),
              "missing_development_people": missing, "search_plan": identity,
              "development_majority_label": int(np.argmax(np.bincount(labels.astype(int), minlength=2))),
              "folds": [{"train": sorted(set(people[t])), "validation": sorted(set(people[v]))} for t, v in folds]}
    write_json(output_dir / "selection-frozen.json", frozen)
    write_json(output_dir / "cv-trials.json", trials)
    pd.DataFrame([{**{k: v for k, v in t.items() if k not in {"cv_mean_person", "parameters"}},
                   "parameters": json.dumps(t["parameters"]), **t["cv_mean_person"]} for t in trials]).to_csv(
                       output_dir / "cv-trials.csv", index=False)
    retained = thin_training_rows(frame, audit["feature_config"]["window_seconds"])
    import mediapipe as mp
    for kind, choice in best.items():
        template = next(t for i, (k, _, t) in enumerate(candidates(), 1) if i == choice["candidate_index"] and k == kind)
        estimator = clone(template).fit(x[retained], labels[retained])
        suffix = hashlib.sha256(json.dumps({"choice": choice, "feature_version": FEATURE_VERSION,
                                            "features_sha256": sha256_file(features)}, sort_keys=True).encode()).hexdigest()[:8]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        artifact = {"format": ARTIFACT_FORMAT, "kind": kind, "model_version": f"{kind}-nthu-{feature_group}-{stamp[:8]}-{suffix}",
                    "feature_version": FEATURE_VERSION, "feature_names": names, "feature_config": audit["feature_config"],
                    "estimator": estimator, "threshold": choice["threshold"],
                    "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                                 "numpy": np.__version__, "joblib": joblib.__version__},
                    "mediapipe_version": mp.__version__, "landmarker_sha256": audit["landmarker_sha256"],
                    "label_mapping": {"ALERT": 0, "DROWSY": 1}, "trained_at_utc": stamp,
                    "score_kind": "uncalibrated vote fraction" if kind == "rf" else "decision margin",
                    "features_sha256": sha256_file(features), "training_windows": len(retained),
                    "source_dataset": "NTHU-DDD Kaggle local copy; frame_fraction labels"}
        joblib.dump(artifact, output_dir / f"{kind}.joblib")
        if kind == selected_kind:
            joblib.dump(artifact, output_dir / "selected.joblib")
    write_json(output_dir / "artifact-manifest.json", {p.name: sha256_file(p) for p in output_dir.glob("*.joblib")})
    print(f"Frozen selection: {selected_kind}; CV targets met={selection_rank(best[selected_kind]['cv_mean_person'])[0]}", flush=True)


def evaluate(features, plan_path, run_dir, reference_model=None):
    run_dir = Path(run_dir)
    if (run_dir / "report.json").exists():
        raise ValueError("Held-out evaluation already completed; preserve results")
    frozen = json.loads((run_dir / "selection-frozen.json").read_text())
    if frozen.get("heldout_already_inspected", False):
        raise ValueError("Development-only run: previously inspected people cannot be fresh held-out")
    if frozen["search_plan"]["plan_sha256"] != sha256_file(plan_path):
        raise ValueError("Frozen split plan changed")
    frame, audit = load(features)
    if audit["role"] != "fresh_heldout":
        raise ValueError("Evaluation requires fresh held-out features")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if "holdout_manifest_sha256" in plan and audit["manifest_sha256"] != plan["holdout_manifest_sha256"]:
        raise ValueError("Fresh held-out manifest changed from frozen plan")
    missing = check_people(frame, plan, "heldout")
    from ml.runtime import DrowsinessModel
    models, predictions = {}, frame[["subject_id", "video_id", "condition", "end_s", "label"]].copy()
    paths = {"rf": run_dir / "rf.joblib", "svm": run_dir / "svm.joblib"}
    if reference_model:
        paths["uta_v2_frozen_reference"] = Path(reference_model)
    for name, path in paths.items():
        if name in {"rf", "svm"}:
            hashes = json.loads((run_dir / "artifact-manifest.json").read_text())
            if hashes[path.name] != sha256_file(path):
                raise ValueError("Frozen model artifact changed")
        runtime = DrowsinessModel(path)
        if (asdict(runtime.config) != audit["feature_config"]
                or runtime.feature_version != audit["feature_version"]):
            raise ValueError("Reference and test feature windows/config differ")
        scores = score_model(runtime.estimator, frame[runtime.feature_names].to_numpy(dtype=float), runtime.kind)
        if not np.isfinite(scores).all():
            raise ValueError("Non-finite held-out scores")
        predicted = (scores >= runtime.threshold).astype(int)
        predictions[f"{name}_score"], predictions[f"{name}_prediction"] = scores, predicted
        models[name] = {"model_version": runtime.model_version, "threshold": runtime.threshold,
                        "test": metrics(frame.label.to_numpy(), predicted),
                        "mean_person": person_summary(frame.label.to_numpy(), predicted, frame.subject_id.to_numpy()),
                        "per_condition": {c: metrics(g.label.to_numpy(), predicted[g.index]) for c, g in frame.groupby("condition")},
                        "per_person": {p: metrics(g.label.to_numpy(), predicted[g.index]) for p, g in frame.groupby("subject_id")}}
    majority_predictions = np.full(len(frame), frozen["development_majority_label"], dtype=int)
    majority_baseline = metrics(frame.label.to_numpy(), majority_predictions)
    predictions.to_csv(run_dir / "test_predictions.csv", index=False)
    report = {"selected_kind": frozen["selected_kind"], "selection_before_heldout": True, "models": models,
              "selected_cv_targets_met": bool(selection_rank(frozen["best"][frozen["selected_kind"]]["cv_mean_person"])[0]),
              "development_majority_baseline": majority_baseline,
              "missing_heldout_people": missing, "heldout_people": sorted(set(frame.subject_id)),
              "extraction": audit, "limitations": ["Only pure-label, quality-admitted windows evaluated; report exclusions and coverage",
                  "Correlated windows; not independent incidents or false alarms per minute",
                  "NTHU staged/IR conditions differ from real webcam and UTA; no direct accuracy-gain claim across datasets",
                  "No camera, actuator or event-delay acceptance test"]}
    write_json(run_dir / "report.json", report)
    lines = ["# NTHU fresh-person evaluation", "", "Selection frozen on development people before this evaluation.", "",
             "| Model | Accuracy | Macro F1 | DROWSY recall | FPR |", "|---|---:|---:|---:|---:|"]
    for name, model in models.items():
        m = model["test"]
        tn, fp = m["confusion_matrix"][0]
        lines.append(f"| {name} | {m['accuracy']:.4f} | {m['macro_f1']:.4f} | {m['per_class']['DROWSY']['recall']:.4f} | {fp/max(tn+fp,1):.4f} |")
    lines += ["", f"Selected from CV: {frozen['selected_kind']}; test not used to change selection.", "",
              f"Development CV targets met: {report['selected_cv_targets_met']}.", "",
              *[f"- {s}" for s in report["limitations"]]]
    lines += ["", "## Held-out window coverage", "",
              "| Condition | Source videos | Decode quarantines | Candidate windows | Quality rejected | Mixed labels | Evaluated |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for condition, counts in audit.get("coverage_by_condition", {}).items():
        lines.append(f"| {condition} | {counts['source_videos']} | {counts['decode_quarantined_videos']} | "
                     f"{counts['candidate_windows']} | {counts['quality_rejected_windows']} | "
                     f"{counts['ambiguous_windows']} | {counts['accepted_windows']} |")
    (run_dir / "comparison.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    plot_confusions(models, run_dir)
    print("\n".join(lines), flush=True)


def plot_confusions(models, run_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, len(models), figsize=(5*len(models), 4), squeeze=False)
    for axis, (name, result) in zip(axes[0], models.items()):
        matrix = np.asarray(result["test"]["confusion_matrix"])
        axis.imshow(matrix, cmap="Blues")
        for row in range(2):
            for col in range(2):
                axis.text(col, row, str(matrix[row, col]), ha="center", va="center",
                          color="white" if matrix[row, col] > matrix.max()/2 else "black")
        axis.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["Not drowsy", "Drowsy"],
                 yticklabels=["Not drowsy", "Drowsy"], xlabel="Predicted", ylabel="Original frame-window label",
                 title=name)
    figure.suptitle("NTHU fresh people: quality-admitted pure-label windows")
    figure.tight_layout()
    figure.savefig(Path(run_dir) / "confusion_matrices.png", dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("select", "evaluate"))
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--reference-model", type=Path)
    parser.add_argument("--feature-group", choices=("eyes", "full"), default="eyes")
    args = parser.parse_args()
    if args.phase == "select":
        select(args.features, args.plan, args.run_dir, args.feature_group)
    else:
        evaluate(args.features, args.plan, args.run_dir, args.reference_model)


if __name__ == "__main__":
    main()
