"""Compare gap-history development OOF predictions on common/recovered windows."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.dataset import sha256_file
from ml.features import FEATURE_GROUPS, FEATURE_VERSION, LEGACY_FEATURE_VERSION
from ml.nthu import write_json
from ml.nthu_train import load, person_summary
from ml.optimize import selection_rank
from ml.train import metrics


def indexed(frame):
    frame = frame.copy()
    frame["endpoint_us"] = (frame.end_s * 1_000_000).round().astype("int64")
    if frame.duplicated(["subject_id", "video_id", "endpoint_us"]).any():
        raise ValueError("Duplicate window identity at microsecond resolution")
    return frame.set_index(["subject_id", "video_id", "endpoint_us"], drop=False).rename_axis(
        ["subject_key", "video_key", "endpoint_key"])


def summary(rows, predicted):
    if not len(rows):
        return None
    labels, people = rows.label.to_numpy(dtype=int), rows.subject_id.to_numpy()
    predicted = np.asarray(predicted, dtype=int)
    pooled = metrics(labels, predicted)
    tn, fp, fn, tp = np.asarray(pooled["confusion_matrix"]).ravel()
    return {"windows": len(rows), "positive_windows": int(tp+fn), "negative_windows": int(tn+fp),
        "pooled": pooled, "pooled_recall": float(tp/(tp+fn)) if tp+fn else None,
        "pooled_fpr": float(fp/(tn+fp)) if tn+fp else None,
        "mean_person": person_summary(labels, predicted, people) if tp+fn and tn+fp else None}


def compare(old_features, new_features, old_run, new_run, plan_path, output):
    old_run, new_run, output = Path(old_run), Path(new_run), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "report.json").exists():
        raise ValueError("Recovery comparison exists; preserve it")
    old, old_audit = load(old_features, expected_version=LEGACY_FEATURE_VERSION)
    current, current_audit = load(new_features)
    if old_audit["role"] != "development" or current_audit["role"] != "development":
        raise ValueError("Recovery comparison accepts development windows only")
    if (old_audit["manifest_sha256"] != current_audit["manifest_sha256"]
            or old_audit["feature_config"] != current_audit["feature_config"]
            or set(old.subject_id) != set(current.subject_id)):
        raise ValueError("People, source manifest or window settings changed")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    old_report = json.loads((old_run / "report.json").read_text(encoding="utf-8"))
    if (plan["parent_ablation_report_sha256"] != sha256_file(old_run / "report.json")
            or plan["parent_oof_sha256"] != sha256_file(old_run / "development_oof_predictions.csv")
            or plan["parent_features_sha256"] != sha256_file(old_features)):
        raise ValueError("Frozen comparison baseline changed")
    frozen = json.loads((new_run / "selection-frozen.json").read_text(encoding="utf-8"))
    if (frozen["search_plan"]["plan_sha256"] != sha256_file(plan_path)
            or frozen["search_plan"]["features_sha256"] != sha256_file(new_features)
            or frozen["folds"] != old_report["folds"]
            or not frozen.get("heldout_already_inspected", False)):
        raise ValueError("Selection identity/folds/known-heldout policy changed")
    hashes = json.loads((new_run / "artifact-manifest.json").read_text())
    if not hashes or any(sha256_file(new_run / name) != value for name, value in hashes.items()):
        raise ValueError("Current model artifact changed")
    previous = indexed(pd.read_csv(old_run / "development_oof_predictions.csv",
                                   dtype={"subject_id": str, "video_id": str}))
    old, current = indexed(old), indexed(current)
    if set(previous.index) != set(old.index) or not np.array_equal(previous.loc[old.index].label, old.label):
        raise ValueError("Old OOF rows do not match old feature labels")
    common = old.index.intersection(current.index).sort_values()
    recovered, lost = current.index.difference(old.index).sort_values(), old.index.difference(current.index).sort_values()
    if not len(common):
        raise ValueError("No common development windows")
    if (not np.array_equal(old.loc[common].label, current.loc[common].label)
            or not np.array_equal(old.loc[common].video_sha256, current.loc[common].video_sha256)):
        raise ValueError("Source or original labels changed on common windows")
    names = list(FEATURE_GROUPS["full"])
    delta = np.abs(old.loc[common, names].to_numpy()-current.loc[common, names].to_numpy())
    baseline_key = old_report["selected"]
    baseline_column = baseline_key.replace("/", "_")+"_prediction"
    baseline = {"model": baseline_key,
        "all_previous": summary(old, previous.loc[old.index, baseline_column].to_numpy()),
        "common": summary(old.loc[common], previous.loc[common, baseline_column].to_numpy())}
    results = {}
    predictions = current[["subject_id", "video_id", "end_s", "condition", "label"]].copy()
    predictions["cohort"] = np.where(predictions.index.isin(common), "common", "recovered")
    for kind, choice in frozen["best"].items():
        cache_key = hashlib.sha256(json.dumps({"identity": frozen["search_plan"], "kind": kind,
            "parameters": choice["parameters"]}, sort_keys=True).encode()).hexdigest()
        with np.load(new_run / "cv-cache" / f"{cache_key}.npz") as cache:
            scores = cache["scores"]
        if len(scores) != len(current) or not np.isfinite(scores).all():
            raise ValueError("Invalid current OOF scores")
        predicted = pd.Series((scores >= choice["threshold"]).astype(int), index=current.index)
        if person_summary(current.label.to_numpy(), predicted.to_numpy(), current.subject_id.to_numpy()) != choice["cv_mean_person"]:
            raise ValueError("Current OOF scores differ from frozen CV selection")
        predictions[f"{kind}_score"], predictions[f"{kind}_prediction"] = scores, predicted
        results[kind] = {"choice": choice, "all_current": summary(current, predicted),
            "common": summary(current.loc[common], predicted.loc[common]),
            "recovered": summary(current.loc[recovered], predicted.loc[recovered]),
            "per_condition": {c: summary(g, predicted.loc[g.index]) for c, g in current.groupby("condition")},
            "per_person": {p: summary(g, predicted.loc[g.index]) for p, g in current.groupby("subject_id")}}
    chosen = frozen["selected_kind"]
    feature_delta = {"max_absolute_by_feature": dict(zip(names, delta.max(axis=0).tolist())),
                     "common_rows_changed_at_1e_minus_6": int((delta > 1e-6).any(axis=1).sum())}
    counts = {key: sum(v[key] for v in current_audit["videos"]) for key in (
        "candidate_windows", "quality_rejected_windows", "ambiguous_windows", "accepted_windows")}
    quality, targets = {}, {}
    for v in current_audit["videos"]:
        for reason, n in v.get("quality_reasons", {}).items():
            quality[reason] = quality.get(reason, 0)+n
        for reason, labels in v.get("targets_by_quality", {}).items():
            for label, n in labels.items():
                target = targets.setdefault(reason, {})
                target[label] = target.get(label, 0)+n
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "feature_version": FEATURE_VERSION,
        "selected_kind": chosen, "selected_cv_targets_met": bool(selection_rank(frozen["best"][chosen]["cv_mean_person"])[0]),
        "common_windows": len(common), "recovered_windows": len(recovered), "lost_windows": len(lost),
        "old_windows": len(old), "current_windows": len(current), "coverage_counts": counts,
        "development_people": int(current.subject_id.nunique()),
        "source_videos": len(current_audit["videos"]), "window_seconds": current_audit["feature_config"]["window_seconds"],
        "quality_reasons": quality, "original_labels_by_quality_reason": targets,
        "feature_delta_on_common": feature_delta, "baseline": baseline, "models": results,
        "previous_coverage_by_condition": old_audit["coverage_by_condition"],
        "current_coverage_by_condition": current_audit["coverage_by_condition"],
        "source": {"old_features_sha256": sha256_file(old_features), "new_features_sha256": sha256_file(new_features),
                   "plan_sha256": sha256_file(plan_path)},
        "limitations": ["Development OOF used for tuning; not independent acceptance metrics",
            "Common-window comparison separates evaluation coverage, but training data and selected parameters also change",
            "Recovered windows have no old predictions; no valid before/after accuracy comparison on that cohort",
            "Conditional window FPR is not false alert incidents per minute; windows overlap",
            "No previously viewed test data loaded; no live camera acceptance or default model promotion"]}
    write_json(output / "report.json", report)
    predictions.to_csv(output / "development_oof_predictions.csv", index=False)
    write_report(report, output)
    plot_common(report, output)
    print(f"Recovery comparison complete: common={len(common)}, recovered={len(recovered)}, lost={len(lost)}", flush=True)
    return report


def write_report(report, output):
    def cell(value):
        return "n/a" if value is None else f"{value*100:.2f}%"
    lines = ["# Giữ lịch sử quanh khoảng mất mặt — kết quả phát triển NTHU", "",
        f"Cùng {report['development_people']} người, {report['source_videos']} video và 4 fold theo người. "
        f"Giữ cửa sổ {report['window_seconds']:g} giây, độ phủ tối thiểu 80% và nhãn gốc.", "",
        f"Cửa sổ cũ: **{report['old_windows']}**; mới: **{report['current_windows']}**; "
        f"chung: **{report['common_windows']}**; phục hồi: **{report['recovered_windows']}**; mất thêm: **{report['lost_windows']}**.", "",
        "## So sánh trên các cửa sổ chung", "",
        "| Model / cách giữ lịch sử | Accuracy gộp | Macro F1 gộp | Recall gộp | FPR gộp |", "|---|---:|---:|---:|---:|"]
    entries = [("Cũ / "+report["baseline"]["model"], report["baseline"]["common"])]
    entries += [("Mới / "+k, v["common"]) for k, v in report["models"].items()]
    for name, m in entries:
        lines.append(f"| {name} | {cell(m['pooled']['accuracy'])} | {m['pooled']['macro_f1']:.4f} | "
            f"{cell(m['pooled_recall'])} | {cell(m['pooled_fpr'])} |")
    lines += ["", "Các model được train bằng dữ liệu tương ứng; bảng này giữ cố định tập cửa sổ được chấm.", "",
        "## Toàn bộ cửa sổ mới và phần phục hồi", "",
        "| Model / tập được chấm | Cửa sổ | Nhãn âm | Nhãn dương | Accuracy | Macro F1 | Recall | FPR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for kind, result in report["models"].items():
        for key, title in (("all_current", "toàn bộ"), ("recovered", "phục hồi")):
            m = result[key]
            if m:
                lines.append(f"| {kind} / {title} | {m['windows']} | {m['negative_windows']} | {m['positive_windows']} | "
                    f"{cell(m['pooled']['accuracy'])} | {m['pooled']['macro_f1']:.4f} | {cell(m['pooled_recall'])} | {cell(m['pooled_fpr'])} |")
    selected = report["models"][report["selected_kind"]]["choice"]["cv_mean_person"]
    lines += ["", f"Chọn bằng CV: **{report['selected_kind']}**. Trung bình theo người: "
        f"Macro F1 **{selected['macro_f1']:.4f}**, recall **{cell(selected['drowsy_recall'])}**, "
        f"FPR **{cell(selected['false_positive_rate'])}**.", "",
        f"Đạt mục tiêu CV trung bình theo người (recall ≥75%, FPR ≤30%): **{report['selected_cv_targets_met']}**.", "",
        "Không trộn chỉ số trung bình theo người với chỉ số gộp cửa sổ.", "",
        "## Nguyên nhân cửa sổ còn bị loại", ""]
    lines += [f"- `{reason}`: {n} cửa sổ." for reason, n in sorted(report["quality_reasons"].items())]
    lines += ["", "## Giới hạn", "",
        "Đây là kết quả CV để chọn model, chưa phải nghiệm thu trên người mới. Phần phục hồi không có dự đoán cũ để đối chiếu.",
        "Giữ độ phủ tối thiểu 80%; khoảng mất mặt không được tính thành mở mắt hay nhắm mắt và luôn ngắt thời gian nhắm liên tục.",
        "Model cũ dùng đúng thuật toán v2 khi nạp lại. Camera mặc định không được chuyển model tự động."]
    (Path(output) / "comparison.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def plot_common(report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    selected = report["selected_kind"]
    entries = [("Previous / "+report["baseline"]["model"], report["baseline"]["common"]),
               ("Gap history / "+selected, report["models"][selected]["common"])]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for axis, (name, m) in zip(axes, entries):
        matrix = np.asarray(m["pooled"]["confusion_matrix"])
        axis.imshow(matrix, cmap="Blues")
        for row in range(2):
            for col in range(2):
                axis.text(col, row, str(matrix[row, col]), ha="center", va="center",
                    color="white" if matrix[row, col] > matrix.max()/2 else "black")
        axis.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["Not drowsy", "Drowsy"],
            yticklabels=["Not drowsy", "Drowsy"], xlabel="Predicted", ylabel="Original label", title=name)
    fig.suptitle(f"Development OOF: {report['common_windows']} common windows (tuning results)")
    fig.tight_layout()
    fig.savefig(Path(output) / "common_windows_confusion.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-features", type=Path, required=True)
    parser.add_argument("--new-features", type=Path, required=True)
    parser.add_argument("--old-run", type=Path, required=True)
    parser.add_argument("--new-run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    compare(args.old_features, args.new_features, args.old_run, args.new_run, args.plan, args.output_dir)
