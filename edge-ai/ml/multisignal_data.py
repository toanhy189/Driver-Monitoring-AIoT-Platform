"""Prepare original auxiliary NTHU labels and resumable private ROI samples.

python -m ml.multisignal_data --output-dir ml-runs/multisignal-v1 --workers 4
No webcam, broker, user queues, video relabelling or physical outputs.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import time
import zipfile

import cv2
import mediapipe as mp
import numpy as np

from config import TASK_PATH
from eye import calculate_average_ear
from face_detection import FaceLandmarkDetector
from head_pose import HeadPoseEstimator
from ml.dataset import sha256_file
from ml.prepare_nthu import member_key
from ml.regions import REGION_VERSION, extract_regions

FORMAT = "nthu-multisignal-roi-v1"
LABEL_REFERENCE = "https://www.csie.ntu.edu.tw/~fuh/personal/DetectionofDriverDrowsinessUsingMulti-TaskLearning.pdf"
LABELS = {"eye": {"0": "NORMAL", "1": "SLEEPY"},
          "mouth": {"0": "NORMAL", "1": "YAWN", "2": "TALKING_LAUGHING"},
          "head": {"0": "NORMAL", "1": "NODDING", "2": "LOOKING_ASIDE"},
          "drowsiness": {"0": "NOT_DROWSY", "1": "DROWSY"}}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def parse_auxiliary(raw, kind):
    content = "".join(raw.decode("utf-8-sig").split())
    if not content or set(content) - set(LABELS[kind]):
        raise ValueError(f"Invalid original {kind} annotation")
    return content


def prepare(catalog_path, manifest_path, output, sample_hz):
    output.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    with manifest_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    dev_subjects = sorted({row["subject_id"] for row in rows if row["role"] == "development"})
    random.Random(20261110).shuffle(dev_subjects)
    if len(dev_subjects) < 16:
        raise ValueError("Need enough separate people for CNN, fusion and validation")
    # Stacking uses different people from the CNN fit. The existing held-out
    # cohort has been inspected in earlier project work and is disclosed as such.
    groups = {"cnn_train": dev_subjects[:10], "fusion_train": dev_subjects[10:14],
              "validation": dev_subjects[14:], "historical_test": sorted({
                  row["subject_id"] for row in rows if row["role"] == "heldout"})}
    lock = {"format": FORMAT, "region_version": REGION_VERSION, "sample_hz": sample_hz,
            "groups": groups, "manifest_sha256": sha256_file(manifest_path),
            "label_reference": LABEL_REFERENCE, "label_mapping": LABELS,
            "landmarker_sha256": sha256_file(TASK_PATH), "mediapipe_version": mp.__version__,
            "opencv_version": cv2.__version__, "python": platform.python_version(),
            "historical_test_previously_inspected": True,
            "provenance": catalog.get("copy_provenance", "Local user-provided Kaggle copy; exact listing unconfirmed"),
            "eye_label_warning": "SLEEPY is not equivalent to physically closed eyes",
            "partial_mask_policy": "Missing crops stay unavailable; no missing frame is normal/open"}
    lock_path = output / "data-plan.json"
    if lock_path.exists() and json.loads(lock_path.read_text(encoding="utf-8")) != lock:
        raise ValueError("Locked dataset plan changed; use a new output directory")
    write_json(lock_path, lock)
    archives = [(zipfile.ZipFile(item["path"]), item["role"]) for item in catalog["archives"]]
    try:
        index = {}
        for archive, role in archives:
            for name in archive.namelist():
                for kind in LABELS:
                    if name.lower().endswith(f"_{kind}.txt"):
                        key = (role, member_key(name), kind)
                        if key in index:
                            raise ValueError("Ambiguous original auxiliary labels")
                        index[key] = (archive, name)
        jobs, quarantine = [], []
        for row in rows:
            if row["status"] != "READY_FOR_FEATURE_EXTRACTION":
                quarantine.append({"video_id": row["video_id"], "reason": row.get("issue", "Prior quarantine")})
                continue
            # Prepared paths may contain absolute roots; subject + condition +
            # original annotation name provide the archive's unambiguous key.
            subject = row["subject_id"].removeprefix("nthu-")
            source_key = member_key(f"{subject}/{row['condition']}/{Path(row['annotation_path']).name}")
            values, hashes = {}, {}
            try:
                for kind in LABELS:
                    archive, name = index[(row["role"], source_key, kind)]
                    raw = archive.read(name)
                    values[kind] = parse_auxiliary(raw, kind)
                    hashes[kind] = hashlib.sha256(raw).hexdigest()
                lengths = {len(value) for value in values.values()}
                if len(lengths) != 1 or next(iter(lengths)) != int(row["annotation_frames"]):
                    raise ValueError("Auxiliary label/frame counts differ")
                with Path(row["annotation_path"]).open("rb") as original:
                    if parse_auxiliary(original.read(), "drowsiness") != values["drowsiness"]:
                        raise ValueError("Prepared drowsiness annotation differs from archive")
            except (KeyError, ValueError) as error:
                quarantine.append({"video_id": row["video_id"], "reason": str(error)})
                continue
            label_path = output / "labels" / f"{row['video_id']}.json"
            label_path.parent.mkdir(exist_ok=True)
            write_json(label_path, values)
            group = next(key for key, subjects in groups.items() if row["subject_id"] in subjects)
            jobs.append({"video_id": row["video_id"], "subject_id": row["subject_id"],
                "condition": row["condition"], "group": group, "video_path": row["video_path"],
                "labels": str(label_path.resolve()), "label_hashes": hashes,
                "output": str(output.resolve()), "sample_hz": sample_hz,
                "landmarker_sha256": lock["landmarker_sha256"]})
        write_json(output / "jobs.json", jobs)
        write_json(output / "prepare-quarantine.json", quarantine)
        return jobs
    finally:
        for archive, _ in archives:
            archive.close()


def extract_job(job):
    cv2.setNumThreads(1)
    output = Path(job["output"]) / "videos" / job["video_id"]
    report = output / "samples.json"
    video_hash = sha256_file(job["video_path"])
    fingerprint = hashlib.sha256(json.dumps({**job, "video_sha256": video_hash,
        "region_version": REGION_VERSION}, sort_keys=True).encode()).hexdigest()
    if report.exists():
        cached = json.loads(report.read_text(encoding="utf-8"))
        if cached["fingerprint"] != fingerprint:
            raise ValueError("Extraction source changed; use a fresh output directory")
        return {"video_id": job["video_id"], "status": cached["status"], "samples": len(cached["samples"]), "cached": True}
    output.mkdir(parents=True, exist_ok=True)
    labels = json.loads(Path(job["labels"]).read_text(encoding="utf-8"))
    count = len(labels["drowsiness"])
    cap = cv2.VideoCapture(job["video_path"], cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    detector = FaceLandmarkDetector()
    head = HeadPoseEstimator()
    rows, error, previous, origin, due, duplicates = [], None, None, None, 0., 0
    index = 0
    started = time.monotonic()
    try:
        if not cap.isOpened():
            raise ValueError("Cannot open video")
        while cap.grab():
            pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            frame_index = index
            index += 1
            if frame_index >= count:
                raise ValueError("Decoded video exceeds annotation length")
            if not math.isfinite(pts) or (previous is not None and pts < previous):
                raise ValueError("Invalid or backwards source timestamp")
            if previous is not None and pts == previous:
                duplicates += 1
                if duplicates > 30:
                    raise ValueError("Too many duplicate source timestamps")
                continue
            previous = pts
            if origin is None:
                origin = pts
            now = pts - origin
            if now + 1e-8 < due:
                continue
            due += 1 / job["sample_hz"]
            ok, frame = cap.retrieve()
            if not ok:
                raise ValueError("Sample frame decode failed")
            faces = detector.process(frame, timestamp_ms=round(now * 1000))
            entry = {"frame_index": frame_index, "time_s": now,
                     **{kind: int(text[frame_index]) for kind, text in labels.items()},
                     "eyes_path": None, "mouth_path": None, "ear": None, "mar": None,
                     "yaw": None, "pitch": None, "eye_sharpness": 0., "mouth_sharpness": 0.}
            if faces:
                face = faces[0]
                regions = extract_regions(frame, face)
                entry.update({key: regions[key] for key in ("mar", "eye_sharpness", "mouth_sharpness")})
                try:
                    ear = calculate_average_ear(face, (frame.shape[1], frame.shape[0]))
                    entry["ear"] = float(ear) if math.isfinite(ear) else None
                except (ValueError, ZeroDivisionError):
                    pass
                pose = head.estimate(face, (frame.shape[1], frame.shape[0]))
                if pose and all(math.isfinite(pose[key]) for key in ("yaw", "pitch")):
                    entry.update(yaw=float(pose["yaw"]), pitch=float(pose["pitch"]))
                for region in ("eyes", "mouth"):
                    crop = regions[region]
                    if crop is not None:
                        image_path = output / f"{frame_index:07d}-{region}.jpg"
                        if not cv2.imwrite(str(image_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                            raise OSError("Cannot save private region image")
                        entry[f"{region}_path"] = str(image_path.resolve())
            rows.append(entry)
        if index != count or (index and duplicates / index > .001):
            raise ValueError("Full decode/label alignment or duplicate PTS audit failed")
    except (ValueError, OSError) as failure:
        error = str(failure)
    finally:
        cap.release()
        detector.close()
    status = "QUARANTINED" if error else "READY"
    write_json(report, {"format": FORMAT, "region_version": REGION_VERSION, "fingerprint": fingerprint,
        "video_sha256": video_hash, "video_id": job["video_id"], "subject_id": job["subject_id"],
        "condition": job["condition"], "group": job["group"], "label_hashes": job["label_hashes"],
        "status": status, "error": error, "decoded_frames": index, "annotation_frames": count,
        "elapsed_seconds": round(time.monotonic() - started, 3), "samples": rows})
    return {"video_id": job["video_id"], "status": status, "samples": len(rows), "error": error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("ml-data/nthu-20261107-catalog/audit.json"))
    parser.add_argument("--manifest", type=Path, default=Path("ml-data/nthu-20261107-prepared/manifest.csv"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-hz", type=float, default=3.)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not 2 <= args.sample_hz <= 10 or not 1 <= args.workers <= 6:
        raise ValueError("Expected 2-10 samples/sec and 1-6 workers")
    jobs = prepare(args.catalog, args.manifest, args.output_dir, args.sample_hz)
    print(json.dumps({"prepared_videos": len(jobs), "groups": dict(Counter(job["group"] for job in jobs))}), flush=True)
    if args.limit:
        jobs = jobs[:args.limit]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        future_jobs = {pool.submit(extract_job, job): job for job in jobs}
        for future in as_completed(future_jobs):
            result = future.result()
            results.append(result)
            print(json.dumps({"completed": len(results), "total": len(jobs), **result}), flush=True)
            write_json(args.output_dir / "extraction-progress.json", results)
    write_json(args.output_dir / "extraction-summary.json", {"videos": results,
        "groups": dict(Counter(job["group"] for job in jobs)), "complete": len(jobs) == len(results) and not args.limit})


if __name__ == "__main__":
    main()
