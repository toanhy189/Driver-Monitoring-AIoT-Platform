"""Counterfactual replay of the restored EAR branch on saved observations.

No camera, inference, training, network or hardware. This checks routing/timers
on previously inspected measurements; a fresh full-camera trial is still needed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from analyze_multisignal_trial import split_attempts, summarize
from ml.multisignal_v2_features import finite
from service.alert_policy import AlertPolicy
from service.multisignal_eye_guard import build_eye_guard, current_guard_ear, runtime_version


def replay(rows, metadata):
    if metadata.get("calibration_used") or metadata.get("binary_eye_changes_policy"):
        raise ValueError("Replay requires an uncalibrated base trial, without prototype decisions")
    if metadata.get("eye_guard", {}).get("enabled"):
        raise ValueError("Source already used an EAR guard")
    guard, info = build_eye_guard(metadata["condition"])
    version = runtime_version(metadata["model_version"], info)
    policy = AlertPolicy("private-offline-replay", version)
    output, events, previous = [], [], None
    for row in rows:
        now = row["elapsed_monotonic"]
        if previous is not None and now <= previous:
            raise ValueError("Nonmonotonic source observations")
        gap = previous is not None and now-previous > .5
        previous = now
        signals = row["signals"]
        if signals.get("eye_closure_state") != "DISABLED":
            raise ValueError("Source observations already used an EAR guard")
        face = row["face_detected"]
        ear = row.get("ear_raw")
        admitted = (signals.get("ear_available") and signals.get("eye_quality") == "VALID"
                    and finite(ear, 0, .8))
        guard_ear = current_guard_ear(ear if admitted else None, row.get("head"))
        if gap or not face:
            if guard: guard.reset()
            raw, reason = "UNKNOWN", "FRAME_GAP" if gap else "NO_FACE"
        elif guard and guard.update(now, guard_ear):
            raw, reason = "DROWSY", "EYE_CLOSURE_RISK"
        else:
            raw, reason = row["raw_state"], row["reason"]
        for event in policy.update(raw, valid=face, now=now, observed_at=row["utc"]):
            if event["event_type"].endswith("THRESHOLD_REACHED"):
                events.append({"phase": row["phase"], "phase_stage": row["phase_stage"],
                               "phase_elapsed_s": row["phase_elapsed_s"],
                               "level": event["level"], "event_type": event["event_type"],
                               "state_duration_ms": event["state_duration_ms"]})
        output.append({**row, "raw_state": raw, "reason": reason,
                       "confirmed_state": policy.state, "model_version": version})
    return {"model_version": version, "base_model_version": metadata["model_version"],
            "eye_guard": info, "source_rows": len(rows),
            "attempts": [summarize(attempt) for attempt in split_attempts(output)],
            "debug_policy_events": events, "raw_counts": Counter(r["raw_state"] for r in output),
            "limits": ["Counterfactual using stored EAR, crop admission, pose and RF decisions; no inference rerun.",
                       "Same inspected session; not fresh acceptance or independent accuracy.",
                       "Fixed historical 0.20/1s rule; no threshold selection or fitting on this recording.",
                       "User action phases are prompts, not independently labeled frame truth.",
                       "Closure during PREP can activate the guard before MEASURING begins.",
                       "Recovery can include the existing 1s guard release and 2s policy confirmation."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError("Do not overwrite a prior review")
    if not (args.trial/"summary.json").exists(): raise ValueError("Close the source trial first with Q")
    metadata = json.loads((args.trial/"trial.json").read_text(encoding="utf-8"))
    data = (args.trial/"observations.jsonl").read_bytes()
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    result = replay(rows, metadata)
    result.update(source_trial=str(args.trial), source_observations_sha256=hashlib.sha256(data).hexdigest())
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({"status": "OFFLINE_GUARD_REPLAY_COMPLETE", "output": str(args.output),
                      "model_version": result["model_version"]}))


if __name__ == "__main__": main()
