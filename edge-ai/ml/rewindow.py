"""Build 5/10/20s tables from corrected observations, using identical endpoints.

No image decoding, no invented labels/timestamps. The common 20s quality gate
is explicit: comparisons only concern endpoints admitted for all three windows.
"""

import argparse
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path

from ml.baseline import BaselineReplay
from ml.dataset import sha256_file
from ml.extract import write_json
from ml.features import FEATURE_NAMES, FEATURE_VERSION, FeatureConfig, FeatureWindow


def rewindow(source_dir, output_dir, windows=(5, 10, 20)):
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    audit = json.loads((source_dir / "extraction.json").read_text(encoding="utf-8"))
    if audit["feature_version"] != FEATURE_VERSION:
        raise ValueError("Need corrected v2 observations; never reuse v1 geometry")
    if output_dir.exists():
        raise ValueError("Output exists; choose a new directory to preserve the audit")
    configs = {s: FeatureConfig(**{**audit["feature_config"], "window_seconds": float(s)}) for s in windows}
    tables, audits = {s: [] for s in windows}, {s: [] for s in windows}
    for video in audit["videos"]:
        cache = source_dir / video["cache"]
        observations = json.loads(cache.read_text(encoding="utf-8"))["observations"]
        trackers = {s: FeatureWindow(c) for s, c in configs.items()}
        baseline = BaselineReplay(configs[10])
        due, rejected, accepted, next_end = 0, 0, 0, float(max(windows))
        for now, ear, yaw, pitch in observations:
            if not all(v is not None and math.isfinite(v) for v in (ear, yaw, pitch)):
                # Match main.py: a degenerate face is missing for the rule too.
                ear = None
            pose = {"yaw": yaw, "pitch": pitch}
            for tracker in trackers.values():
                tracker.add(now, ear, pose)
            prediction = baseline.update(now, ear)
            if now + 1e-8 < next_end:
                continue
            next_end = now + audit["feature_config"]["stride_seconds"]
            due += 1
            snapshots = {s: t.snapshot(now) for s, t in trackers.items()}
            if prediction is None or any(v is None for v in snapshots.values()):
                rejected += 1
                continue
            accepted += 1
            for s, snapshot in snapshots.items():
                tables[s].append({"subject_id": video["subject_id"], "video_id": video["video_id"],
                    "video_sha256": video["video_sha256"], "label": 0 if video["label"] == "ALERT" else 1,
                    "start_s": snapshot["start_s"], "end_s": snapshot["end_s"],
                    "coverage": snapshot["coverage"], "baseline_prediction": prediction,
                    **snapshot["features"]})
        for s in windows:
            audits[s].append({**video, "accepted_windows": accepted, "candidate_windows": due,
                "rejected_windows": rejected, "observations_sha256": sha256_file(cache)})
        print(f"Rewindow {video['video_id']}: common={accepted}, rejected={rejected}", flush=True)
    for s in windows:
        folder = output_dir / f"window-{s}"
        folder.mkdir(parents=True)
        path = folder / "features.csv"
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=("subject_id", "video_id", "video_sha256", "label",
                "start_s", "end_s", "coverage", "baseline_prediction", *FEATURE_NAMES))
            writer.writeheader()
            writer.writerows(tables[s])
        metadata = {k: v for k, v in audit.items() if k not in {"videos", "features_sha256", "feature_config"}}
        write_json(folder / "extraction.json", {**metadata, "feature_config": asdict(configs[s]),
            "features_sha256": sha256_file(path), "videos": audits[s],
            "common_quality_gate_seconds": max(windows), "source_extraction_sha256": sha256_file(source_dir / "extraction.json")})
    return {s: output_dir / f"window-{s}" / "features.csv" for s in windows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rewindow(args.source_dir, args.output_dir)


if __name__ == "__main__":
    main()
