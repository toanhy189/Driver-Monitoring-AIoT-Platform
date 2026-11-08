"""Extract private per-window CSV features from reviewed video labels.

Run from edge-ai: python -m ml.extract --manifest ... --output-dir ...
Per-video caches allow resuming a batch. No face images/landmarks are exported.
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import time

import cv2
import mediapipe as mp

from config import TASK_PATH
from eye import calculate_average_ear
from face_detection import FaceLandmarkDetector
from head_pose import HeadPoseEstimator
from ml.baseline import BaselineReplay
from ml.dataset import LABELS, read_manifest, sha256_file
from ml.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig, FeatureWindow


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def extract_video(path, config, timestamp_source="pts", max_seconds=None, progress_label=None,
                  allow_duplicate_pts=False):
    # Bound decoder threads when several videos run concurrently.
    if hasattr(cv2, "CAP_PROP_N_THREADS"):
        capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    else:
        capture = cv2.VideoCapture(str(path))
    detector = None
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open video: {path}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        expected_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if timestamp_source == "frame-index" and (not math.isfinite(fps) or fps <= 0):
            raise ValueError("Constant-frame-rate fallback requires a valid FPS")
        detector = FaceLandmarkDetector()
        head = HeadPoseEstimator()
        window, baseline = FeatureWindow(config), BaselineReplay(config)
        index, sampled, rejected, due_count = 0, 0, 0, 0
        last_pts, origin, next_sample, next_window = None, None, 0.0, config.window_seconds
        rows, observations, candidate_audit = [], [], []
        quality_reasons = Counter()
        duplicate_pts_skipped = 0
        last_progress = time.monotonic()
        while True:
            # Decode each frame for accurate PTS, but only materialize sampled
            # BGR images. This avoids converting/copying unused full-HD frames.
            if not capture.grab():
                break
            position = (capture.get(cv2.CAP_PROP_POS_MSEC) / 1000 if timestamp_source == "pts"
                        else index / fps)
            index += 1
            if allow_duplicate_pts and last_pts is not None and position == last_pts:
                # A zero-duration duplicate has no new presentation instant.
                # Drop it, retaining source PTS for every admitted observation.
                duplicate_pts_skipped += 1
                if duplicate_pts_skipped > 30:
                    raise ValueError("Too many duplicate PTS frames; inspect source video")
                continue
            if not math.isfinite(position) or (last_pts is not None and position <= last_pts):
                raise ValueError("Non-increasing video PTS. Inspect the file; only use "
                                 "--timestamp-source frame-index for confirmed constant-FPS video.")
            last_pts = position
            if origin is None:
                origin = position
            now = position - origin
            if max_seconds is not None and now > max_seconds:
                break
            if now + 1e-8 < next_sample:
                continue
            next_sample = now + 1 / config.sample_hz
            ok, frame = capture.retrieve()
            if not ok:
                raise ValueError(f"Cannot retrieve sampled frame {index}")
            faces = detector.process(frame, timestamp_ms=round(now * 1000))
            ear, pose = None, None
            if faces:
                frame_size = (frame.shape[1], frame.shape[0])
                ear = float(calculate_average_ear(faces[0], frame_size))
                pose = head.estimate(faces[0], frame_size)
                if not math.isfinite(ear):
                    ear, pose = None, None
            observations.append([now, ear, pose.get("yaw") if pose else None,
                                 pose.get("pitch") if pose else None])
            window.add(now, ear, pose)
            prediction = baseline.update(now, ear)
            sampled += 1
            if now + 1e-8 >= next_window:
                due_count += 1
                snapshot = window.snapshot()
                quality_reasons[window.last_quality_reason] += 1
                candidate_audit.append({"start_s": now-config.window_seconds, "end_s": now,
                                        "quality_reason": window.last_quality_reason})
                if snapshot is not None:
                    rows.append({"start_s": snapshot["start_s"], "end_s": snapshot["end_s"],
                                 "coverage": snapshot["coverage"],
                                 "baseline_prediction": -1 if prediction is None else prediction,
                                 **snapshot["features"]})
                else:
                    rejected += 1
                next_window = now + config.stride_seconds
            if progress_label and time.monotonic() - last_progress >= 30:
                print(f"Progress {progress_label}: video={now:.0f}s, sampled={sampled}, "
                      f"accepted={len(rows)}, rejected={rejected}", flush=True)
                last_progress = time.monotonic()
        if index == 0:
            raise ValueError("Video contains no readable frames")
        if duplicate_pts_skipped / index > 0.001:
            raise ValueError("Duplicate PTS exceeds 0.1% of decoded frames; inspect source video")
        if max_seconds is None and expected_frames > 0 and index < expected_frames - 2:
            raise ValueError("Video decode ended early; refusing partial extraction")
        return {"rows": rows, "observations": observations, "candidate_audit": candidate_audit,
                "quality_reasons": dict(quality_reasons),
                "decoded_frames": index, "sampled_frames": sampled,
                "rejected_windows": rejected, "candidate_windows": due_count,
                "duplicate_pts_skipped": duplicate_pts_skipped,
                "allow_duplicate_pts": allow_duplicate_pts,
                "last_source_second": None if last_pts is None else last_pts - origin}
    finally:
        capture.release()
        if detector is not None:
            detector.close()


def extract_cached_video(job):
    video, settings, output_dir = job
    video_hash = sha256_file(video["resolved_path"])
    key = hashlib.sha256(json.dumps({**settings, "video_sha256": video_hash},
                                   sort_keys=True).encode()).hexdigest()
    cache = Path(output_dir) / f"cache-{key}.json"
    # Strict-PTS caches have already proved there are no duplicate timestamps;
    # their observations also satisfy the opt-in duplicate-tolerant policy.
    legacy_cache = None
    if settings.get("allow_duplicate_pts"):
        strict_settings = {k: v for k, v in settings.items() if k != "allow_duplicate_pts"}
        strict_key = hashlib.sha256(json.dumps({**strict_settings, "video_sha256": video_hash},
                                               sort_keys=True).encode()).hexdigest()
        legacy_cache = Path(output_dir) / f"cache-{strict_key}.json"
    if cache.exists():
        result = json.loads(cache.read_text(encoding="utf-8"))
    elif legacy_cache is not None and legacy_cache.exists():
        result = json.loads(legacy_cache.read_text(encoding="utf-8"))
        result.setdefault("duplicate_pts_skipped", 0)
        result.setdefault("allow_duplicate_pts", False)
        write_json(cache, result)
    else:
        print(f"Starting {video['video_id']}", flush=True)
        result = extract_video(video["resolved_path"], FeatureConfig(**settings["feature_config"]),
                               settings["timestamp_source"], settings["max_seconds"],
                               progress_label=video["video_id"],
                               allow_duplicate_pts=settings.get("allow_duplicate_pts", False))
        write_json(cache, result)
    return video, video_hash, cache.name, result


def extract(manifest, output_dir, config=None, timestamp_source="pts", max_seconds=None, workers=1,
            cache_only=False, allow_duplicate_pts=False):
    config = config or FeatureConfig()
    if not isinstance(workers, int) or not 1 <= workers <= 8:
        raise ValueError("workers must be an integer from 1 to 8")
    if max_seconds is not None and (not math.isfinite(max_seconds) or max_seconds <= config.window_seconds):
        raise ValueError("max-seconds must exceed the feature window")
    videos = read_manifest(manifest)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = {"feature_version": FEATURE_VERSION, "feature_config": asdict(config),
                "timestamp_source": timestamp_source, "max_seconds": max_seconds,
                "landmarker_sha256": sha256_file(TASK_PATH), "mediapipe_version": mp.__version__,
                "opencv_version": cv2.__version__}
    if allow_duplicate_pts:
        if timestamp_source != "pts":
            raise ValueError("Duplicate PTS handling requires source PTS mode")
        settings["allow_duplicate_pts"] = True
    all_rows, audit, completed = [], [], {}
    jobs = [(video, settings, str(output_dir)) for video in videos]
    if workers == 1:
        for job in jobs:
            result = extract_cached_video(job)
            completed[result[0]["video_id"]] = result
            print(f"Completed {len(completed)}/{len(videos)}: {result[0]['video_id']}", flush=True)
    else:
        # Release all native decoder/MediaPipe state between source videos.
        executor = ProcessPoolExecutor(max_workers=workers, max_tasks_per_child=1)
        futures = {executor.submit(extract_cached_video, job): job[0]["video_id"] for job in jobs}
        try:
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"FAILED {futures[future]}: {exc}", flush=True)
                    raise
                completed[result[0]["video_id"]] = result
                print(f"Completed {len(completed)}/{len(videos)}: {result[0]['video_id']}", flush=True)
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
    if cache_only:
        # Helpers can fill independent per-video caches without replacing the
        # final CSV/audit owned by the complete manifest's extraction process.
        return output_dir
    seen_hashes = set()
    for number, video in enumerate(videos, 1):
        _, video_hash, cache_name, result = completed[video["video_id"]]
        if video_hash in seen_hashes:
            raise ValueError("Identical video bytes appear twice; review subject IDs and labels")
        seen_hashes.add(video_hash)
        for row in result["rows"]:
            all_rows.append({"subject_id": video["subject_id"], "video_id": video["video_id"],
                             "video_sha256": video_hash, "label": LABELS[video["label"]], **row})
        audit.append({"subject_id": video["subject_id"], "video_id": video["video_id"],
                      "video_sha256": video_hash, "label": video["label"],
                      "label_source": video["label_source"], "cache": cache_name,
                      **{k: v for k, v in result.items() if k not in {"rows", "observations"}},
                      "accepted_windows": len(result["rows"])})
        print(f"[{number}/{len(videos)}] {video['video_id']}: accepted={len(result['rows'])}, "
              f"rejected={result['rejected_windows']}", flush=True)
    path = output_dir / "features.csv"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=("subject_id", "video_id", "video_sha256", "label",
                                "start_s", "end_s", "coverage", "baseline_prediction", *FEATURE_NAMES))
        writer.writeheader()
        writer.writerows(all_rows)
    write_json(output_dir / "extraction.json", {**settings, "manifest_sha256": sha256_file(manifest),
               "features_sha256": sha256_file(path), "videos": audit,
               "note": "Video-level weak labels; not frame-onset ground truth"})
    if not all_rows:
        raise ValueError("No valid feature windows. Inspect extraction.json; no training data produced.")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timestamp-source", choices=("pts", "frame-index"), default="pts")
    parser.add_argument("--max-seconds", type=float, help="Pilot only: truncate each video explicitly")
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--stride-seconds", type=float, default=2.0)
    parser.add_argument("--sample-hz", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=1, help="Parallel video processes (1-8); start with 2")
    parser.add_argument("--cache-only", action="store_true", help="Fill per-video caches without assembling CSV/audit")
    parser.add_argument("--allow-duplicate-pts", action="store_true",
                        help="Skip exact duplicate PTS only (max 30 frames and 0.1%%); never rewrite time")
    args = parser.parse_args()
    print(f"Extractor PID: {os.getpid()}", flush=True)
    try:
        extract(args.manifest, args.output_dir,
                FeatureConfig(window_seconds=args.window_seconds, stride_seconds=args.stride_seconds,
                              sample_hz=args.sample_hz), args.timestamp_source, args.max_seconds, args.workers,
                args.cache_only, args.allow_duplicate_pts)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
