"""Compare eyes/full on identical development folds; never load test features."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.dataset import sha256_file
from ml.nthu import write_json
from ml.nthu_train import load, select, person_summary
from ml.optimize import selection_rank
from ml.train import metrics


def run(features, source_plan, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(source_plan).read_text(encoding="utf-8"))
    plan["status"] = "development ablation; previous held-out results already inspected"
    plan["candidate_search_proposal"]["feature_groups"] = ["eyes", "full"]
    plan["evaluation_policy"] = "Development CV tuning only. Previously viewed people are regression, not independent acceptance."
    plan["parent_plan_sha256"] = sha256_file(source_plan)
    path = output / "plan.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Ablation plan changed; choose a new directory")
    write_json(path, plan)
    frame, audit = load(features)
    if audit["role"] != "development":
        raise ValueError("Ablation requires development features")
    results, folds = {}, None
    predictions = frame[["subject_id", "video_id", "condition", "end_s", "label"]].copy()
    for group in ("eyes", "full"):
        directory = output / group
        if not (directory / "artifact-manifest.json").exists():
            select(features, path, directory, group)
        frozen = json.loads((directory / "selection-frozen.json").read_text(encoding="utf-8"))
        if frozen["search_plan"]["features_sha256"] != sha256_file(features):
            raise ValueError("Features changed since selection")
        if frozen["search_plan"]["plan_sha256"] != sha256_file(path):
            raise ValueError("Plan changed since selection")
        hashes = json.loads((directory / "artifact-manifest.json").read_text())
        if any(sha256_file(directory / name) != value for name, value in hashes.items()):
            raise ValueError("Ablation artifact changed")
        if folds is not None and frozen["folds"] != folds:
            raise ValueError("Ablation must compare identical person folds")
        folds = frozen["folds"]
        for kind, choice in frozen["best"].items():
            key = hashlib.sha256(json.dumps({"identity": frozen["search_plan"], "kind": kind,
                "parameters": choice["parameters"]}, sort_keys=True).encode()).hexdigest()
            with np.load(directory / "cv-cache" / f"{key}.npz") as data:
                scores = data["scores"]
            predicted = (scores >= choice["threshold"]).astype(int)
            if person_summary(frame.label.to_numpy(), predicted, frame.subject_id.to_numpy()) != choice["cv_mean_person"]:
                raise ValueError("Selected out-of-fold predictions changed")
            predictions[f"{group}_{kind}_score"] = scores
            predictions[f"{group}_{kind}_prediction"] = predicted
            results[f"{group}/{kind}"] = {**choice, "feature_group": group,
                "features": len(frozen["search_plan"]["features"]),
                "pooled_oof": metrics(frame.label.to_numpy(), predicted),
                "per_condition": {c: metrics(g.label.to_numpy(), predicted[g.index]) for c, g in frame.groupby("condition")},
                "per_person": {p: metrics(g.label.to_numpy(), predicted[g.index]) for p, g in frame.groupby("subject_id")}}
    selected = max(results, key=lambda key: selection_rank(results[key]["cv_mean_person"]))
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "selected": selected,
        "targets_met": bool(selection_rank(results[selected]["cv_mean_person"])[0]),
        "results": results, "folds": folds, "features_sha256": sha256_file(features),
        "limitations": ["Development CV used for tuning and selection; not unbiased acceptance accuracy",
            "Only quality-admitted pure-label windows; feature groups use exactly the same rows",
            "No fresh-person evaluation and no camera model promotion in this experiment"]}
    write_json(output / "report.json", report)
    predictions.to_csv(output / "development_oof_predictions.csv", index=False)
    lines = ["# So sánh đặc trưng trên tập phát triển NTHU", "",
        "Cùng 14 người, 4 fold tách theo người, cùng cửa sổ 20 giây và cùng tập dòng dữ liệu.", "",
        "| Đặc trưng / mô hình | Số đặc trưng | Macro F1 | Recall DROWSY | FPR | Ngưỡng |",
        "|---|---:|---:|---:|---:|---:|"]
    for key, choice in results.items():
        m = choice["cv_mean_person"]
        lines.append(f"| {key} | {choice['features']} | {m['macro_f1']:.4f} | "
            f"{m['drowsy_recall']:.4f} | {m['false_positive_rate']:.4f} | {choice['threshold']:.2f} |")
    lines += ["", f"Chọn theo quy tắc CV đã chốt: **{selected}**.", "",
        f"Đạt đồng thời recall ≥ 75% và FPR ≤ 30% trên trung bình theo người: **{report['targets_met']}**.", "",
        "Các tỷ lệ trên lấy trung bình theo người có lớp tương ứng, không phải gộp tất cả cửa sổ.", "",
        "## Đối chiếu khi gộp tất cả cửa sổ ngoài fold", "",
        "| Đặc trưng / mô hình | Accuracy | Macro F1 | Recall DROWSY | FPR |",
        "|---|---:|---:|---:|---:|"]
    for key, choice in results.items():
        m = choice["pooled_oof"]
        tn, fp = m["confusion_matrix"][0]
        lines.append(f"| {key} | {m['accuracy']:.4f} | {m['macro_f1']:.4f} | "
            f"{m['per_class']['DROWSY']['recall']:.4f} | {fp/max(tn+fp,1):.4f} |")
    lines += ["", "Không trộn hai cách tính tỷ lệ. Chỉ số gộp chịu ảnh hưởng số cửa sổ mỗi người và lệch lớp.", "",
        "Đây là số liệu dùng để chọn mô hình. Chưa phải kết quả nghiệm thu trên người mới.",
        "Không đọc lại tập test, không đổi mô hình camera mặc định."]
    (output / "comparison.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"Ablation complete: {selected}; targets_met={report['targets_met']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.features, args.plan, args.output_dir)
