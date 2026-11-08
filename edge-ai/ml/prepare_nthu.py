"""Audit local NTHU-DDD ZIP copies and prepare frame-labelled video manifests.

No network, webcam, training or relabelling. Video names never supply labels.
Development and held-out people must be disjoint. Unequal video/annotation frame
counts are quarantined, never silently truncated or stretched to fit.
"""

import argparse
from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile

from ml.dataset import sha256_file

GIB = 1024 ** 3
SOURCE = "https://cv.cs.nthu.edu.tw/php/callforpaper/datasets/DDD/"
LABEL_REFERENCE = "https://www.csie.ntu.edu.tw/~fuh/personal/DetectionofDriverDrowsinessUsingMulti-TaskLearning.pdf"
FIELDS = ("dataset", "subject_id", "video_id", "role", "condition", "video_path",
          "annotation_path", "label_source", "video_sha256", "annotation_sha256",
          "fps", "video_frames_header", "annotation_frames", "not_drowsy_frames",
          "drowsy_frames", "status", "issue")


def safe_member(name):
    path = PurePosixPath(name.replace("\\", "/"))
    if (path.is_absolute() or ".." in path.parts or len(path.parts) < 2
            or any(":" in part for part in path.parts) or not path.parts[0].isdigit()):
        raise ValueError(f"Unsafe or unsupported NTHU member: {name}")
    return path


def member_key(name):
    """Handle training AVI names and evaluation *_mix / *_mixing aliases."""
    path = safe_member(name)
    stem = path.stem
    stem = re.sub(r"_(drowsiness|eye|head|mouth)$", "", stem, flags=re.I)
    stem = re.sub(rf"^{re.escape(path.parts[0])}_", "", stem)
    stem = stem.lower().replace("mixing", "mix")
    return re.sub(r"[^a-z0-9]", "", "/".join((*path.parts[:-1], stem)).lower())


def condition_for(name):
    text = re.sub(r"[^a-z0-9]", "", name.lower())
    for condition in ("nightnoglasses", "nightglasses", "sunglasses", "noglasses", "glasses"):
        if condition in text:
            return condition
    raise ValueError(f"Unknown capture condition: {name}")


def parse_labels(data):
    text = "".join(data.decode("utf-8-sig").split())
    if not text or set(text) - {"0", "1"}:
        raise ValueError("Drowsiness annotation must contain one binary digit per frame")
    return text


def collect(archive, archive_path, role):
    labels = {}
    videos = []
    for item in archive.infolist():
        if item.is_dir():
            continue
        suffix = PurePosixPath(item.filename).suffix.lower()
        if suffix not in {".txt", ".avi", ".mp4", ".mov", ".mkv"}:
            continue
        path = safe_member(item.filename)
        if stat.S_ISLNK(item.external_attr >> 16):
            raise ValueError("Archive symlinks are not supported")
        if path.name.lower().endswith("_drowsiness.txt"):
            key = member_key(item.filename)
            if key in labels:
                raise ValueError("Ambiguous duplicate annotation key")
            labels[key] = item
        elif suffix != ".txt":
            videos.append(item)
    result, paired = [], set()
    for item in sorted(videos, key=lambda v: v.filename):
        annotation = labels.get(member_key(item.filename))
        if annotation is None:
            raise ValueError(f"Missing frame annotation: {item.filename}")
        if annotation.filename in paired:
            raise ValueError("An annotation is assigned to multiple videos")
        paired.add(annotation.filename)
        sequence = parse_labels(archive.read(annotation))  # zipfile also verifies CRC32.
        result.append({"archive_path": str(archive_path), "role": role,
                       "subject_id": "nthu-" + safe_member(item.filename).parts[0],
                       "condition": condition_for(item.filename),
                       "video_member": item.filename, "annotation_member": annotation.filename,
                       "video_crc32": item.CRC, "video_bytes": item.file_size,
                       "annotation_sha256": hashlib.sha256(archive.read(annotation)).hexdigest(),
                       "annotation_frames": len(sequence),
                       "not_drowsy_frames": sequence.count("0"), "drowsy_frames": sequence.count("1")})
    if not result or set(labels) != {member_key(n) for n in paired}:
        raise ValueError("Empty archive or unpaired drowsiness annotation")
    return result


def validate_roles(entries):
    roles, signatures = {}, {}
    for entry in entries:
        person, role = entry["subject_id"], entry["role"]
        if person in roles and roles[person] != role:
            raise ValueError("Subject leakage between development and held-out archives")
        roles[person] = role
        signature = (entry["video_crc32"], entry["video_bytes"])
        if signature in signatures:
            raise ValueError("Duplicate video bytes/signature in input archives; review copies")
        signatures[signature] = person


def copy_member(archive, name, root):
    path = safe_member(name)
    destination = root.joinpath(*path.parts)
    # Resolve existing symlinks before writing, including symlinked parent folders.
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("Destination escapes the dataset root")
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Refusing to overwrite existing dataset member: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("Partial destination already exists; inspect it before retrying")
    digest = hashlib.sha256()
    try:
        with archive.open(name) as source, temporary.open("xb") as output:
            while block := source.read(1024 * 1024):
                digest.update(block)
                output.write(block)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, digest.hexdigest()


def video_metadata(path):
    import cv2
    capture = cv2.VideoCapture(str(path))
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if (not capture.isOpened() or not math.isfinite(fps) or fps <= 0
                or not math.isfinite(count) or count < 1 or abs(count - round(count)) > 1e-4):
            raise ValueError("Invalid video header/FPS")
        ok, _ = capture.read()
        if not ok:
            raise ValueError("Cannot decode first frame")
        return fps, round(count)
    finally:
        capture.release()


def prepare(development_zips, holdout_zips, output_dir, root, *, extract=False, max_gib=8.0):
    if not math.isfinite(max_gib) or max_gib <= 0:
        raise ValueError("max_gib must be finite and positive")
    inputs = [(Path(p).resolve(), role) for role, paths in (
        ("development", development_zips), ("heldout", holdout_zips)) for p in paths]
    if not development_zips or not holdout_zips or len({p for p, _ in inputs}) != len(inputs):
        raise ValueError("Provide distinct development and held-out ZIP archives")
    output_dir, root = Path(output_dir).resolve(), Path(root).resolve()
    if output_dir.exists():
        raise ValueError("Output directory exists; preserve the previous audit and choose a new directory")
    with ExitStack() as stack:
        archives = {p: stack.enter_context(zipfile.ZipFile(p)) for p, _ in inputs}
        entries = [entry for p, role in inputs for entry in collect(archives[p], p, role)]
        validate_roles(entries)
        total_bytes = sum(e["video_bytes"] + archives[Path(e["archive_path"])].getinfo(
            e["annotation_member"]).file_size for e in entries)
        if total_bytes > max_gib * GIB:
            raise ValueError("Prepared dataset exceeds size budget; no files extracted")
        if extract:
            existing = next((root.joinpath(*safe_member(e[k]).parts)
                             for e in entries for k in ("video_member", "annotation_member")
                             if root.joinpath(*safe_member(e[k]).parts).exists()
                             or root.joinpath(*safe_member(e[k]).parts).is_symlink()), None)
            if existing:
                raise ValueError(f"Refusing to overwrite existing dataset: {existing}")
            ancestor = root
            while not ancestor.exists():
                ancestor = ancestor.parent
            if shutil.disk_usage(ancestor).free < total_bytes + 10 * GIB:
                raise ValueError("Insufficient disk space; preserve at least 10 GiB free")
        output_dir.mkdir(parents=True)
        rows = []
        for number, entry in enumerate(entries, 1):
            video_path = root.joinpath(*safe_member(entry["video_member"]).parts)
            annotation_path = root.joinpath(*safe_member(entry["annotation_member"]).parts)
            row = {"dataset": "NTHU-DDD-local-Kaggle-copy", "subject_id": entry["subject_id"],
                   "video_id": "nthu-" + member_key(entry["video_member"]),
                   "role": entry["role"], "condition": entry["condition"],
                   "video_path": str(video_path), "annotation_path": str(annotation_path),
                   "label_source": "provided frame-level *_drowsiness.txt; 0=not-drowsy,1=drowsy",
                   "annotation_sha256": entry["annotation_sha256"],
                   **{k: entry[k] for k in ("annotation_frames", "not_drowsy_frames", "drowsy_frames")},
                   "video_sha256": "", "fps": "", "video_frames_header": "",
                   "status": "CATALOG_ONLY", "issue": ""}
            if extract:
                archive = archives[Path(entry["archive_path"])]
                _, row["video_sha256"] = copy_member(archive, entry["video_member"], root)
                _, copied_hash = copy_member(archive, entry["annotation_member"], root)
                if copied_hash != entry["annotation_sha256"]:
                    raise ValueError("Annotation checksum changed")
                try:
                    row["fps"], row["video_frames_header"] = video_metadata(video_path)
                    if row["video_frames_header"] != row["annotation_frames"]:
                        raise ValueError("Frame count differs from annotation length; no automatic resampling")
                    row["status"] = "READY_FOR_FEATURE_EXTRACTION"
                except (ValueError, RuntimeError) as error:
                    row["status"], row["issue"] = "QUARANTINED", str(error)
                if number % 25 == 0 or number == len(entries):
                    print(f"Prepared {number}/{len(entries)} videos", flush=True)
            rows.append(row)
        if extract and len({r["video_sha256"] for r in rows}) != len(rows):
            raise ValueError("Identical video SHA-256 across records; review before use")
        for name, subset in (("manifest.csv", rows), ("development.csv", [r for r in rows if r["role"] == "development"]),
                             ("heldout.csv", [r for r in rows if r["role"] == "heldout"]),
                             ("quarantine.csv", [r for r in rows if r["status"] == "QUARANTINED"])):
            with (output_dir / name).open("w", newline="", encoding="utf-8") as target:
                writer = csv.DictWriter(target, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(subset)
        summary = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "source_reference": SOURCE,
                   "annotation_reference": LABEL_REFERENCE,
                   "copy_provenance": "User reports Kaggle NTHU-DDD; exact listing URL not supplied; not authenticated against author checksums",
                   "archives": [{"path": str(p), "role": role, "bytes": p.stat().st_size} for p, role in inputs],
                   "roles": {role: {"subjects": sorted({r["subject_id"] for r in rows if r["role"] == role}),
                                     "videos": sum(r["role"] == role for r in rows)} for role in ("development", "heldout")},
                   "videos": len(rows), "uncompressed_gib": total_bytes / GIB,
                   "conditions": dict(Counter(r["condition"] for r in rows)),
                   "statuses": dict(Counter(r["status"] for r in rows)),
                   "label_frames": dict(Counter({"not_drowsy": sum(r["not_drowsy_frames"] for r in rows),
                                                 "drowsy": sum(r["drowsy_frames"] for r in rows)})),
                   "heldout_policy": "Freeze subjects before feature/model selection; do not use heldout labels/scores for tuning",
                   "limits": ["Header frame-count equality and first-frame decode only; full decode/PTS audit still required",
                              "NTHU non-drowsy is not necessarily ATTENTIVE; no DISTRACTED labels inferred",
                              "Frame-labelled manifest is not compatible with the UTA whole-video manifest loader",
                              "IR/night videos do not validate an ordinary RGB webcam in darkness",
                              "No model trained, no accuracy improvement claimed, no webcam opened"]}
        (output_dir / "audit.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
        (output_dir / "split-lock.json").write_text(json.dumps({"created_at_utc": summary["created_at_utc"],
            "manifest_sha256": sha256_file(output_dir / "manifest.csv"), "roles": summary["roles"],
            "policy": summary["heldout_policy"]}, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("videos", "uncompressed_gib", "statuses", "roles")}, indent=2))
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-zip", type=Path, action="append", required=True)
    parser.add_argument("--holdout-zip", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("datasets/NTHU-DDD"))
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--max-gib", type=float, default=8.0)
    args = parser.parse_args()
    prepare(args.development_zip, args.holdout_zip, args.output_dir, args.root,
            extract=args.extract, max_gib=args.max_gib)


if __name__ == "__main__":
    main()
