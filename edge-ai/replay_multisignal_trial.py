"""Paired offline replay of an existing private recording, never a new acceptance test."""
import argparse
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import math
from pathlib import Path
from unittest.mock import patch

import cv2

from analyze_multisignal_trial import split_attempts, summarize
from diagnose_multisignal import describe
from eye import calculate_average_ear
from face_detection import FaceLandmarkDetector
from head_pose import HeadPoseEstimator, HeadPoseTracker
from ml.multisignal_runtime import load_multisignal_model
from service.alert_policy import AlertPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--condition", choices=("glasses", "no-glasses"),
                        help="Candidate capture condition; baseline remains the frozen no-profile runtime")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Do not overwrite a prior paired replay")
    args.output.mkdir(parents=True)
    cv2.setNumThreads(1)
    source = [json.loads(line) for line in (args.trial/"observations.jsonl").read_text(encoding="utf-8").splitlines()]
    by_frame = {row["frame_index"]: row for row in source}
    origin = datetime.fromisoformat(source[0]["utc"])
    start = source[0]["elapsed_monotonic"]
    clock = [0.]
    models = {"baseline": load_multisignal_model(args.baseline),
              "v2": load_multisignal_model(args.candidate, condition=args.condition)}
    heads = {name: HeadPoseTracker() for name in models}
    policies = {name: AlertPolicy("private-offline-replay", m.model_version, clock=lambda: clock[0],
        utcnow=lambda: origin+timedelta(seconds=clock[0])) for name, m in models.items()}
    rows, warnings = {name: [] for name in models}, {name: Counter() for name in models}
    streams = {name: (args.output/(name+"-observations.jsonl")).open("w", encoding="utf-8") for name in models}
    detector = FaceLandmarkDetector(); estimator = HeadPoseEstimator()
    cap = cv2.VideoCapture(str(args.trial/"raw.avi"))
    if not cap.isOpened():
        detector.close(); raise ValueError("Private recording unavailable")
    index = 0; previous = None; due = 0.
    try:
        with patch("head_pose.time.monotonic", side_effect=lambda: clock[0]), redirect_stdout(io.StringIO()):
            while cap.grab():
                index += 1
                row = by_frame.get(index)
                if not row: continue
                now = row["elapsed_monotonic"]-start
                if now+1e-8 < due: continue
                due = now+.2
                ok, frame = cap.retrieve()
                if not ok: raise ValueError("Recording decode failed")
                clock[0] = now
                faces = detector.process(frame, timestamp_ms=round(now*1000))
                face = faces[0] if faces else None
                ear = calculate_average_ear(face, (frame.shape[1], frame.shape[0])) if face else None
                ear = ear if ear is not None and math.isfinite(ear) else None
                pose = estimator.estimate(face, (frame.shape[1], frame.shape[0])) if face else None
                if pose and not all(math.isfinite(pose[k]) for k in ("yaw", "pitch")): pose = None
                gap = (now-previous)*1000 if previous is not None else None
                for name, model in models.items():
                    if not face or (gap is not None and gap > 500): heads[name].interrupt()
                    status = heads[name].update(pose) if face else None
                    raw = model.observe(frame, face, now, ear, pose, status)
                    events = policies[name].update(raw, valid=bool(face), now=now)
                    warnings[name].update(e["event_type"] for e in events if e["event_type"].endswith("THRESHOLD_REACHED"))
                    out = describe(model, face, status, raw, policies[name], now, gap)
                    out.update(frame_index=index, ear_raw=ear, pose_raw=pose,
                        **{key: row[key] for key in ("phase", "phase_stage", "phase_elapsed_s")})
                    streams[name].write(json.dumps(out, allow_nan=False)+"\n")
                    rows[name].append(out)
                previous = now
    finally:
        cap.release(); detector.close()
        for stream in streams.values(): stream.close()
    result = {"source_trial": str(args.trial), "closure_profile_used": False,
        "candidate_condition": args.condition,
        "sample_hz_max": 5, "models": {name: {"model_version": model.model_version,
            "eye_guard": getattr(model, "guard_metadata", None),
            "attempts": [summarize(x) for x in split_attempts(rows[name])], "warning_counts": warnings[name]}
            for name, model in models.items()},
        "limits": ["Same inspected recording; diagnostic comparison, NOT fresh acceptance or independent test.",
            "Recomputed landmarks and common 5 Hz sampling for both frozen models; original live sampling differed.",
            "User action prompts are not independently labeled per-frame ground truth.",
            "Known incomplete actions/repeated attempts remain separate; no calibration derived from this video.",
            "No webcam, network, physical outputs, new private media, or training on this recording."]}
    (args.output/"comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PAIRED_REPLAY_COMPLETE", "output": str(args.output)}), flush=True)


if __name__ == "__main__": main()
