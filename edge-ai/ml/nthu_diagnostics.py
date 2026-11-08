"""Audit development exclusions, with a bounded deterministic video replay pilot."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path

from ml.dataset import sha256_file
from ml.features import FeatureConfig, FeatureWindow
from ml.nthu import read_manifest, window_target, write_json
from ml.nthu_train import load


def rejection_reason(window, end):
    """Explain the existing snapshot gates without changing feature semantics."""
    if not window.samples:
        return "no_history"
    if window.samples[0].timestamp > end-window.config.window_seconds+1e-7:
        return "insufficient_continuous_history"
    if not window.samples[-1].valid:
        return "invalid_current_observation"
    if end-window.samples[-1].timestamp > window.config.max_gap_seconds:
        return "stale_current_observation"
    observed = 0.
    for a, b in zip(window.samples, list(window.samples)[1:]):
        duration = min(end, b.timestamp)-max(end-window.config.window_seconds, a.timestamp)
        if duration > 0 and a.valid and b.valid and b.timestamp-a.timestamp <= window.config.max_gap_seconds:
            observed += duration
    if observed <= 0 or observed/window.config.window_seconds+1e-8 < window.config.min_coverage:
        return "insufficient_valid_coverage"
    return "accepted_quality"


def pilot_job(row, config_values, audit_dir, output):
    from ml.extract import extract_video
    import numpy as np
    config = FeatureConfig(**config_values)
    if sha256_file(row["video_path"]) != row["video_sha256"]:
        raise ValueError("Pilot video changed")
    if sha256_file(row["annotation_path"]) != row["annotation_sha256"]:
        raise ValueError("Pilot annotation changed")
    result = extract_video(row["video_path"], config, progress_label=row["video_id"])
    frame_key = row["video_sha256"]+"-"+row["annotation_sha256"]
    with np.load(Path(audit_dir) / f"frames-{frame_key}.npz") as source:
        times, labels = source["times"], source["labels"]
    if result["decoded_frames"] != len(labels):
        raise ValueError("Pilot decoder count changed")
    window = FeatureWindow(config)
    due = config.window_seconds
    counts, targets, missing = Counter(), {}, Counter()
    resets = 0
    for now, ear, yaw, pitch in result["observations"]:
        old_valid = window.last_valid
        had_history = bool(window.samples)
        if (window.reset_history_on_face_loss and had_history and old_valid is not None
                and now-old_valid >= config.face_loss_reset_seconds):
            resets += 1
        window.add(now, ear, {"yaw": yaw, "pitch": pitch})
        missing["invalid_ear"] += int(ear is None)
        missing["invalid_pose"] += int(yaw is None or pitch is None)
        if now+1e-8 < due:
            continue
        reason = rejection_reason(window, now)
        snapshot = window.snapshot()
        if (snapshot is not None) != (reason == "accepted_quality"):
            raise ValueError("Diagnostic gates diverged from shared feature implementation")
        counts[reason] += 1
        target, _ = window_target(times, labels, max(0., now-config.window_seconds), now)
        bucket = targets.setdefault(reason, Counter())
        bucket[str(target)] += 1
        due = now+config.stride_seconds
    if sum(counts.values()) != result["candidate_windows"] or counts["accepted_quality"] != len(result["rows"]):
        raise ValueError("Replay candidate counts diverged")
    record = {"video_id": row["video_id"], "condition": row["condition"],
        "subject_id": row["subject_id"], "video_sha256": row["video_sha256"],
        "sampled_frames": result["sampled_frames"], "reset_operations": resets,
        "invalid_observations": missing, "reasons": counts, "original_label_by_reason": targets,
        "note": "First failing gate; resets count operations, not distinct face-loss episodes. -1=mixed labels."}
    write_json(Path(output) / f"pilot-{row['video_id']}.json", record)
    return record


def run(features, manifest, output, workers=2):
    frame, audit = load(features)
    rows = read_manifest(manifest)
    if audit["role"] != "development" or any(r["role"] != "development" for r in rows):
        raise ValueError("Diagnostics pilot accepts development people only")
    if sha256_file(manifest) != audit["manifest_sha256"]:
        raise ValueError("Manifest differs from audited features")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = {r["video_id"]: r for r in rows}
    selected = []
    for condition in sorted(audit["coverage_by_condition"]):
        videos = [v for v in audit["videos"] if v["condition"] == condition and v["candidate_windows"] >= 20]
        selected.append(max(videos, key=lambda v: (v["quality_rejected_windows"]/v["candidate_windows"], v["video_id"])))
    control = min((v for v in audit["videos"] if v["candidate_windows"] >= 20),
        key=lambda v: (v["quality_rejected_windows"]/v["candidate_windows"], v["video_id"]))
    if control not in selected:
        selected.append(control)
    pilot_plan = {"selection": "Worst quality-rejection fraction per condition (>=20 windows), plus best control; development only",
        "features_sha256": sha256_file(features), "feature_config": audit["feature_config"],
        "videos": [source[v["video_id"]] for v in selected]}
    write_json(output / "pilot-plan.json", pilot_plan)
    records = []
    with ProcessPoolExecutor(max_workers=workers, max_tasks_per_child=1) as pool:
        futures = [pool.submit(pilot_job, row, audit["feature_config"], Path(features).parent / "decode-audit", output)
            for row in pilot_plan["videos"]]
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            print(f"Diagnostic pilot: {record['video_id']} {record['reasons']}", flush=True)
    records.sort(key=lambda r: r["video_id"])
    people = []
    for person in sorted({v["subject_id"] for v in audit["videos"]}):
        videos = [v for v in audit["videos"] if v["subject_id"] == person]
        accepted = frame[frame.subject_id == person]
        people.append({"subject_id": person, **{key: sum(v[key] for v in videos) for key in (
            "candidate_windows", "quality_rejected_windows", "ambiguous_windows", "accepted_windows")},
            "negative_windows": int((accepted.label == 0).sum()), "positive_windows": int((accepted.label == 1).sum())})
    report = {"role": "development", "coverage_by_condition": audit["coverage_by_condition"],
        "people": people, "pilot": records, "limitations": ["Pilot selected for extremes; not representative of all videos",
            "First failing gate may hide other simultaneous causes", "No threshold relaxed and no labels changed",
            "Decode count and PTS checks do not certify visually clean pixels"]}
    write_json(output / "report.json", report)
    lines = ["# Chẩn đoán cửa sổ bị loại — tập phát triển", "",
        "| Người | Cửa sổ dự kiến | Loại chất lượng | Nhãn trộn | Giữ lại | Không buồn ngủ | Buồn ngủ |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for p in people:
        lines.append("| "+" | ".join(str(p[k]) for k in ("subject_id", "candidate_windows", "quality_rejected_windows",
            "ambiguous_windows", "accepted_windows", "negative_windows", "positive_windows"))+" |")
    lines += ["", "## Chạy lại video để xác định nguyên nhân", "",
        "Chọn video bị loại nhiều nhất mỗi điều kiện và một video đối chứng. Đây là mẫu cực trị, không đại diện toàn bộ dataset.", "",
        "| Video | Thiếu lịch sử liên tục | Quan sát hiện tại lỗi | Độ phủ thấp | Qua chất lượng |",
        "|---|---:|---:|---:|---:|"]
    for r in records:
        c = r["reasons"]
        lines.append(f"| {r['video_id']} | {c.get('insufficient_continuous_history',0)} | "
            f"{c.get('invalid_current_observation',0)} | {c.get('insufficient_valid_coverage',0)} | {c.get('accepted_quality',0)} |")
    lines += ["", "Thiếu lịch sử: chưa có đủ độ dài cửa sổ. V3 giữ lịch sử theo thời gian; model v2 vẫn dùng reset như cũ.",
        "Quan sát lỗi: EAR hoặc yaw/pitch thiếu/không hữu hạn. Hiện cả hai nhóm đặc trưng đều dùng chung điều kiện này.",
        "Độ phủ thấp: các đoạn quan sát hợp lệ chưa chiếm đủ 80% cửa sổ.",
        "Đếm theo điều kiện thất bại đầu tiên. Không tự giảm ngưỡng chất lượng để làm đẹp chỉ số."]
    (output / "diagnosis.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers must be 1..4")
    run(args.features, args.manifest, args.output_dir, args.workers)
