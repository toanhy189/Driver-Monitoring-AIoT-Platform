"""Frame-labelled NTHU adapter. Audit all decoded frames before using a clip.

Use separate development and held-out manifests. Failed clips stay in the audit;
no timestamp rewriting, label resampling or filename-derived targets is allowed.
"""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import os

import numpy as np

from ml.dataset import sha256_file
from ml.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig
from ml.prepare_nthu import parse_labels


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def read_manifest(path):
    with Path(path).open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or len({r["video_id"] for r in rows}) != len(rows):
        raise ValueError("Empty manifest or duplicate video ID")
    seen_hashes = set()
    for row in rows:
        if row["status"] != "READY_FOR_FEATURE_EXTRACTION":
            raise ValueError("Manifest includes a quarantined source")
        if row["video_sha256"] in seen_hashes:
            raise ValueError("Duplicate video hash")
        seen_hashes.add(row["video_sha256"])
    if len({r["role"] for r in rows}) != 1:
        raise ValueError("Do not mix development and held-out manifests")
    return rows


def window_target(times, labels, start, end):
    """Original frame fraction inside the causal feature window, inclusive endpoints."""
    times, labels = np.asarray(times), np.asarray(labels)
    if len(times) != len(labels) or not len(times) or np.any(np.diff(times) <= 0):
        raise ValueError("Invalid frame/label alignment")
    if not np.isin(labels, [0, 1]).all() or not 0 <= start < end <= times[-1] + 1e-6:
        raise ValueError("Invalid labels/window boundaries")
    left, right = np.searchsorted(times, [start - 1e-8, end + 1e-8], side="left")
    if right <= left:
        raise ValueError("Empty labelled window")
    fraction = float(labels[left:right].mean())
    target = 0 if fraction <= .2 + 1e-12 else 1 if fraction >= .8 - 1e-12 else -1
    return target, fraction


def audit_video(row, output_dir):
    import cv2
    output_dir = Path(output_dir)
    key = row["video_sha256"] + "-" + row["annotation_sha256"]
    path = output_dir / f"audit-{key}.json"
    if sha256_file(row["video_path"]) != row["video_sha256"] or \
            sha256_file(row["annotation_path"]) != row["annotation_sha256"]:
        raise ValueError("Prepared source checksum changed")
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached["opencv_version"] != cv2.__version__:
            raise ValueError("Decoder version changed; audit in a new directory")
        return row, cached
    labels = parse_labels(Path(row["annotation_path"]).read_bytes())
    cap = cv2.VideoCapture(row["video_path"], cv2.CAP_FFMPEG,
                           [cv2.CAP_PROP_N_THREADS, 2])
    times = []
    try:
        if not cap.isOpened():
            raise ValueError("Cannot open prepared video")
        while cap.grab():
            times.append(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000)
    finally:
        cap.release()
    times = np.asarray(times, dtype=float)
    problems = []
    if len(times) != len(labels):
        problems.append("decoded frame count differs from original annotation")
    if not len(times) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        problems.append("non-finite, duplicate or backwards source PTS")
    result = {"video_id": row["video_id"], "subject_id": row["subject_id"],
              "condition": row["condition"], "video_sha256": row["video_sha256"],
              "annotation_sha256": row["annotation_sha256"], "decoded_frames": len(times),
              "annotation_frames": len(labels), "status": "QUARANTINED" if problems else "VALID",
              "issues": problems, "opencv_version": cv2.__version__}
    if not problems:
        times -= times[0]
        result["duration_s"] = float(times[-1])
        np.savez_compressed(output_dir / f"frames-{key}.npz", times=times,
                            labels=np.frombuffer(labels.encode(), dtype=np.uint8) - ord("0"))
    write_json(path, result)
    return row, result


def extract_job(row, audit_dir, output_dir, config):
    import mediapipe as mp
    from config import TASK_PATH
    from ml.extract import extract_video
    if sha256_file(row["video_path"]) != row["video_sha256"] or \
            sha256_file(row["annotation_path"]) != row["annotation_sha256"]:
        raise ValueError("Source changed after decode audit")
    settings = {"feature_version": FEATURE_VERSION, "feature_config": asdict(config),
                "landmarker_sha256": sha256_file(TASK_PATH), "mediapipe_version": mp.__version__}
    identity = {**settings, "video_sha256": row["video_sha256"],
                "annotation_sha256": row["annotation_sha256"]}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = Path(output_dir) / f"features-{key}.json"
    if cache.exists():
        record = json.loads(cache.read_text(encoding="utf-8"))
        if ("observations_cache" in record and
                sha256_file(Path(output_dir) / record["observations_cache"]) != record["observations_sha256"]):
            raise ValueError("Numeric observation cache changed")
        record.update(video_sha256=row["video_sha256"], annotation_sha256=row["annotation_sha256"])
        return row, record
    result = extract_video(Path(row["video_path"]), config, progress_label=row["video_id"])
    frame_key = row["video_sha256"] + "-" + row["annotation_sha256"]
    with np.load(Path(audit_dir) / f"frames-{frame_key}.npz") as frame_data:
        times, labels = frame_data["times"], frame_data["labels"]
    if result["decoded_frames"] != len(labels) or abs(result["last_source_second"] - times[-1]) > 1e-5:
        raise ValueError("Decode changed between audit and feature extraction")
    # Numeric observations support later window experiments without decoding
    # faces again. This private cache contains no images or landmarks.
    observation_path = Path(output_dir) / f"observations-{key}.npz"
    temporary = observation_path.with_suffix(f".{os.getpid()}.tmp")
    with temporary.open("wb") as target:
        np.savez_compressed(target, observations=np.asarray(result["observations"], dtype=float))
    temporary.replace(observation_path)
    targets_by_quality = defaultdict(Counter)
    for candidate in result["candidate_audit"]:
        label, _ = window_target(times, labels, max(0., candidate["start_s"]), candidate["end_s"])
        targets_by_quality[candidate["quality_reason"]][str(label)] += 1
    accepted, ambiguous = [], 0
    for window in result["rows"]:
        label, fraction = window_target(times, labels, max(0., window["start_s"]), window["end_s"])
        if label == -1:
            ambiguous += 1
            continue
        accepted.append({"subject_id": row["subject_id"], "video_id": row["video_id"],
                         "video_sha256": row["video_sha256"], "condition": row["condition"],
                         "label": label, "drowsy_fraction": fraction, **window})
    record = {**settings, "video_id": row["video_id"], "subject_id": row["subject_id"],
              "video_sha256": row["video_sha256"], "annotation_sha256": row["annotation_sha256"],
              "condition": row["condition"], "rows": accepted,
              "observations_cache": observation_path.name,
              "observations_sha256": sha256_file(observation_path),
              "quality_reasons": result["quality_reasons"],
              "targets_by_quality": dict(targets_by_quality),
              "candidate_windows": result["candidate_windows"],
              "quality_rejected_windows": result["rejected_windows"], "ambiguous_windows": ambiguous,
              "accepted_windows": len(accepted), "decoded_frames": result["decoded_frames"]}
    write_json(cache, record)
    return row, record


def run(manifest, output_dir, *, phase="extract", workers=3, config=None):
    if not 1 <= workers <= 8:
        raise ValueError("workers must be 1..8")
    rows = read_manifest(manifest)
    config = config or FeatureConfig(window_seconds=20)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = {"manifest_sha256": sha256_file(manifest), "feature_version": FEATURE_VERSION,
            "feature_config": asdict(config), "label_policy": "frame fraction <=0.2 negative; >=0.8 positive; mixed excluded"}
    plan_path = output_dir / "extraction-plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Extraction plan changed; use a new directory")
    write_json(plan_path, plan)
    audit_dir = output_dir / "decode-audit"
    audit_dir.mkdir(exist_ok=True)
    audited = []
    # Decode audits are lightweight and release their OpenCV state per clip.
    for index, row in enumerate(rows, 1):
        audited.append(audit_video(row, audit_dir))
        if index % 25 == 0 or index == len(rows):
            print(f"Decode audit {index}/{len(rows)}", flush=True)
    write_json(output_dir / "decode-summary.json", [a for _, a in audited])
    valid = [row for row, audit in audited if audit["status"] == "VALID"]
    print(f"Full decode: valid={len(valid)}, quarantined={len(rows)-len(valid)}", flush=True)
    if phase == "audit":
        return
    results, failures = [], []
    with ProcessPoolExecutor(max_workers=workers, max_tasks_per_child=1) as pool:
        futures = {pool.submit(extract_job, row, audit_dir, output_dir, config): row for row in valid}
        for index, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            try:
                _, result = future.result()
                results.append(result)
                print(f"Features {index}/{len(valid)} {row['video_id']}: {result['accepted_windows']}", flush=True)
            except Exception as error:
                failures.append({"video_id": row["video_id"], "error": str(error)})
                print(f"FAILED {row['video_id']}: {error}", flush=True)
    write_json(output_dir / "failures.json", failures)
    if failures:
        raise ValueError("Extraction failures recorded; resume before training; no partial CSV assembled")
    results.sort(key=lambda r: r["video_id"])
    feature_rows = [row for result in results for row in result["rows"]]
    fields = ("subject_id", "video_id", "video_sha256", "condition", "label", "drowsy_fraction",
              "start_s", "end_s", "coverage", "baseline_prediction", *FEATURE_NAMES)
    path = output_dir / "features.csv"
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(feature_rows)
    metadata = {**plan, **({k: results[0][k] for k in ("landmarker_sha256", "mediapipe_version")} if results else {}),
                "features_sha256": sha256_file(path), "videos": [{k: v for k, v in r.items() if k != "rows"} for r in results],
                "decoded_source_videos": len(rows), "decode_quarantined_videos": len(rows)-len(valid),
                "feature_windows": len(feature_rows), "role": rows[0]["role"], "label_type": "frame_fraction"}
    metadata["coverage_by_condition"] = {}
    for condition in sorted({r["condition"] for r in rows}):
        records = [r for r in results if r["condition"] == condition]
        metadata["coverage_by_condition"][condition] = {
            "source_videos": sum(r["condition"] == condition for r in rows),
            "decode_quarantined_videos": sum(a["condition"] == condition and a["status"] != "VALID" for _, a in audited),
            **{k: sum(r[k] for r in records) for k in ("candidate_windows", "quality_rejected_windows", "ambiguous_windows", "accepted_windows")}}
    write_json(output_dir / "extraction.json", metadata)
    if not feature_rows:
        raise ValueError("No eligible windows; inspect decode and quality audits")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("audit", "extract"), default="extract")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    run(args.manifest, args.output_dir, phase=args.phase, workers=args.workers)


if __name__ == "__main__":
    main()
