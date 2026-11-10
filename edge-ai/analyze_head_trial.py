"""Summarize guided head-motion trials without inferring clinical ground truth."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from analyze_multisignal_trial import split_attempts


def summarize(attempt):
    rows = attempt["rows"]
    durations = Counter()
    lost_seconds = 0.
    new_cycles = 0
    pitch = []
    for first, second in zip(rows, rows[1:]):
        if first.get("phase_stage") != "MEASURING" or second.get("phase_stage") != "MEASURING":
            continue
        dt = second["elapsed_monotonic"]-first["elapsed_monotonic"]
        if not 0 < dt <= .5:
            lost_seconds += max(0., dt)
            continue
        a = first.get("signals", {}).get("head_motion") or {}
        b = second.get("signals", {}).get("head_motion") or {}
        durations[a.get("state", "UNAVAILABLE")] += dt
        if a.get("available") and b.get("available"):
            new_cycles += max(0, b["nod_count"]-a["nod_count"])
        if a.get("pitch_deg") is not None:
            pitch.append(a["pitch_deg"])
    measured = [r for r in rows if r.get("phase_stage") == "MEASURING"]
    return dict(phase=attempt["phase"], attempt=attempt["attempt"], measured_rows=len(measured),
        head_state_seconds=dict(durations), gap_seconds_not_scored=lost_seconds,
        new_cycles_during_measuring=new_cycles,
        max_window_nods=max((r.get("signals", {}).get("head_motion", {}).get("nod_count", 0) for r in measured), default=0),
        pitch_quantiles=np.percentile(pitch, [10, 50, 90]).tolist() if pitch else None,
        finished=any(r.get("phase_stage") == "DONE" for r in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(s) for s in (args.trial/"observations.jsonl").read_text(encoding="utf-8").splitlines()]
    report = dict(scope="Guided development actions; operator confirmation required; no clinical labels",
        mode="OBSERVE_ONLY", physical_outputs_used=False,
        attempts=[summarize(a) for a in split_attempts(rows) if a["phase"] != "IDLE"])
    target = args.trial/"head-analysis.json"
    target.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
