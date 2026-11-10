"""Choose temporal thresholds on the already-used validation cohort, not live acceptance.

Copies an RF to a NEW candidate directory; keeps the first candidate immutable.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil

import joblib

from ml.dataset import sha256_file
from ml.multisignal_data import write_json
from ml.multisignal_evaluate import replay, aggregate
from ml.multisignal_v2_features import bundle_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-false-per-hour", type=float, default=5.12)
    args = parser.parse_args()
    old = args.data_dir/"candidate"
    manifest = json.loads((old/"manifest.json").read_text(encoding="utf-8"))
    if manifest["format"] != "driver-multisignal-v2" or args.output.exists():
        raise ValueError("Expected v2 source and a new candidate output")
    for name, digest in manifest["files"].items():
        if sha256_file(old/name) != digest: raise ValueError("Frozen candidate changed")
    artifact = joblib.load(old/"fusion.joblib")
    artifact["estimator"].set_params(n_jobs=1)
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((args.data_dir/"predictions").glob("*.json"))]
    reports = [report for report in reports if report["group"] == "validation"]
    cache = {}; choices = []
    for enter in (.7, .75, .8, .85, .9, .95):
        for margin in (.03, .05, .1):
            leave = round(enter-margin, 6)
            current = {**artifact, "threshold": enter, "leave_threshold": leave}
            scores = [replay(report, manifest, current, prepared_cache=cache) for report in reports]
            metrics = aggregate(scores)
            choice = {"enter": enter, "leave": leave, "validation_replay": metrics}
            choices.append(choice)
            write_json(args.data_dir/"threshold-sweep.json", {"choices": choices, "status": "RUNNING"})
            print(json.dumps({"enter": enter, "leave": leave, "recall": metrics["eligible_interval_recall"],
                "unknown": metrics["unknown_fraction"], "false_per_hour": metrics["false_warning_episodes_per_negative_hour"]}), flush=True)
    eligible = [r for r in choices if r["validation_replay"]["false_warning_episodes_per_negative_hour"] <= args.max_false_per_hour]
    if not eligible:
        write_json(args.data_dir/"threshold-sweep.json", {"choices": choices, "status": "NO_ELIGIBLE_CANDIDATE"})
        raise ValueError("No candidate meets the predefined false warning budget")
    selected = max(eligible, key=lambda r: (r["validation_replay"]["eligible_interval_recall"],
        r["validation_replay"]["positive_time_recall"], -r["validation_replay"]["false_warning_episodes_per_negative_hour"]))
    args.output.mkdir(parents=True)
    artifact.update(threshold=selected["enter"], leave_threshold=selected["leave"])
    joblib.dump(artifact, args.output/"fusion.joblib")
    shutil.copy2(old/"regions.pt", args.output/"regions.pt")
    files = {name: sha256_file(args.output/name) for name in ("regions.pt", "fusion.joblib")}
    final = {**manifest, "files": files, "enter_threshold": selected["enter"], "leave_threshold": selected["leave"],
        "model_version": bundle_version(files, selected["enter"], selected["leave"]),
        "selected_fusion": selected, "selection_method": "validation-temporal-false-alarm-budget",
        "initial_candidate": manifest["model_version"], "fresh_trial_used_for_selection": False}
    write_json(args.output/"manifest.json", final)
    write_json(args.output/"temporal-selection.json", {"selected": selected, "choices": choices,
        "max_false_per_negative_hour": args.max_false_per_hour,
        "limits": ["Same validation cohort as earlier model selection; no independent final test.",
                   "Thresholds frozen before any fresh v2 webcam acceptance.",
                   "Calibrated closure disabled during dataset replay."]})
    write_json(args.data_dir/"threshold-sweep.json", {"choices": choices, "selected": selected, "status": "FROZEN"})
    print(json.dumps({"status": "TEMPORAL_CANDIDATE_FROZEN", "model_version": final["model_version"], "selected": selected}), flush=True)


if __name__ == "__main__": main()
