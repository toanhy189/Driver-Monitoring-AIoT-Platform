"""Build and validate a small, local UTA-RLDD manifest; never download videos."""

import argparse
import csv
import hashlib
from pathlib import Path

LABELS = {"ALERT": 0, "DROWSY": 1}
MANIFEST_FIELDS = ("subject_id", "video_id", "path", "label", "label_source")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path):
    path = Path(path).resolve()
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not set(MANIFEST_FIELDS).issubset(reader.fieldnames or []):
            raise ValueError(f"Manifest requires {MANIFEST_FIELDS}")
        rows = list(reader)
    if not rows:
        raise ValueError("Manifest has no videos")
    seen_ids, seen_paths = set(), set()
    for row in rows:
        if (not all(row.get(k, "").strip() for k in MANIFEST_FIELDS)
                or row["label"] not in LABELS):
            raise ValueError("Empty manifest field or unsupported label (only ALERT/DROWSY)")
        resolved = (path.parent / row["path"]).resolve()
        if not resolved.is_file():
            raise ValueError(f"Video does not exist: {resolved}")
        if row["video_id"] in seen_ids or resolved in seen_paths:
            raise ValueError("Duplicate video ID/path in manifest")
        seen_ids.add(row["video_id"])
        seen_paths.add(resolved)
        row["resolved_path"] = resolved
    return rows


def make_manifest(root, output, subjects=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not root.is_dir():
        raise ValueError(f"Dataset directory does not exist: {root}")
    rows, skipped = [], 0
    for video in sorted(root.rglob("*")):
        if video.suffix.lower() not in VIDEO_EXTENSIONS or not video.is_file():
            continue
        subject = video.parent.name
        if subjects and subject not in subjects:
            continue
        # Supported convention: .../<numeric subject>/<0|5|10>.<extension>.
        # Unknown layouts fail rather than silently inventing ground truth.
        if not subject.isdigit() or video.stem not in {"0", "5", "10"}:
            raise ValueError(f"Unsupported UTA layout: {video}. Use an explicit reviewed manifest.")
        if video.stem == "5":
            skipped += 1
            continue
        rows.append({"subject_id": subject, "video_id": f"uta-{subject}-{video.stem}",
                     "path": str(video), "label": "ALERT" if video.stem == "0" else "DROWSY",
                     "label_source": "UTA-RLDD predominant video label (0/10)"})
    if not rows:
        raise ValueError("No labeled videos found; download a subset first")
    by_subject = {}
    for row in rows:
        by_subject.setdefault(row["subject_id"], []).append(row["label"])
    if subjects and set(subjects) != set(by_subject):
        raise ValueError("Some selected subjects were not found")
    if any(sorted(labels) != ["ALERT", "DROWSY"] for labels in by_subject.values()):
        raise ValueError("Each subject must have exactly one 0 and one 10 video")
    if output.exists():
        raise ValueError("Manifest already exists; choose a new output to preserve the experiment")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Manifest: {len(rows)} videos / {len(by_subject)} subjects; excluded {skipped} low-vigilance videos")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subjects", nargs="+", help="Exact subject folder names, e.g. 01 02 03")
    args = parser.parse_args()
    try:
        make_manifest(args.root, args.output, args.subjects)
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
