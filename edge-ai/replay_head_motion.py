"""Replay private diagnostic AVI/timestamps into head-motion observations only.

No camera, network, database writes, CNN/RF retraining or physical outputs.
Existing guided labels are development evidence, not independent ground truth.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import cv2
import numpy as np

from face_detection import FaceLandmarkDetector
from service.head_motion import CONFIG, VERSION, HeadMotionTracker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=3)
    args = parser.parse_args()
    if args.stride < 1:
        parser.error("stride must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    rows = [json.loads(line) for line in (args.trial/"observations.jsonl").read_text(encoding="utf-8").splitlines()]
    source = cv2.VideoCapture(str(args.trial/"raw.avi"))
    detector = FaceLandmarkDetector(head_motion=True)
    original = FaceLandmarkDetector()
    tracker = HeadMotionTracker()
    states, phases, available = Counter(), {}, 0
    max_landmark_difference = 0.
    compared = 0
    cv2.setNumThreads(1)
    try:
        with (args.output/"observations.jsonl").open("w", encoding="utf-8") as stream:
            for index, row in enumerate(rows):
                ok, frame = source.read()
                if not ok:
                    raise RuntimeError("Private AVI has fewer frames than its timestamp log")
                if index % args.stride:
                    continue
                now = row["elapsed_monotonic"]
                timestamp = round((now-rows[0]["elapsed_monotonic"])*1000)
                faces = detector.process(frame, timestamp_ms=timestamp)
                if compared < 24:
                    old = original.process(frame, timestamp_ms=timestamp)
                    if bool(old) != bool(faces):
                        raise AssertionError("Transformation output changed face availability")
                    if old:
                        delta = np.abs(np.array([[p.x, p.y, p.z] for p in old[0]])-
                                       np.array([[p.x, p.y, p.z] for p in faces[0]])).max()
                        max_landmark_difference = max(max_landmark_difference, float(delta))
                    compared += 1
                head = row.get("head") or {}
                signals = row.get("signals") or {}
                motion = tracker.update(now, detector.head_angles,
                    neutral_allowed=bool(head.get("valid") and not head.get("calibrating", True) and not head.get("is_deviated")),
                    eye_closed=signals.get("eye_closure_state") == "CLOSED_RISK")
                states[motion["state"]] += 1
                available += motion["available"]
                phase = phases.setdefault(row["phase"], Counter())
                phase[motion["state"]] += 1
                stream.write(json.dumps(dict(frame_index=row["frame_index"], phase=row["phase"],
                    phase_stage=row["phase_stage"], head_motion=motion), allow_nan=False)+"\n")
    finally:
        source.release(); detector.close(); original.close()
    report = dict(version=VERSION, mode="OBSERVE_ONLY", config=CONFIG, samples=sum(states.values()),
        available_samples=available, states=dict(states), phase_counts={k:dict(v) for k,v in phases.items()},
        compared_original_landmark_frames=compared, max_original_landmark_difference=max_landmark_difference,
        scope="Replay of existing guided development media; not fresh nod acceptance", mqtt_started=False,
        physical_outputs_used=False, rf_inputs_changed=False)
    (args.output/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
