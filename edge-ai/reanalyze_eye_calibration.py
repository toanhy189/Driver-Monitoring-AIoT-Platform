"""Create a separate development profile from existing numeric measurements.

Never overwrite the source, change its review, tune on repeated phases or open
the camera/network. The new fit method still needs a fresh camera trial.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from service.eye_calibration import geometry_hashes, PHASES
from service.eye_closure_guard import EyeClosureGuard
from service.multisignal_calibration import analyze


def reanalyze(source, output, *, closed_actions_confirmed=False):
    source, output = Path(source), Path(output)
    if output.exists(): raise ValueError("Use a new output directory; source profiles are preserved")
    report_bytes = (source/"report.json").read_bytes()
    old = json.loads(report_bytes)
    source_hash = hashlib.sha256(report_bytes).hexdigest()
    review = source/"fresh-trial-review.json"
    if review.exists():
        data = json.loads(review.read_text(encoding="utf-8"))
        if (data.get("format") != "eye-guard-trial-review-v1"
                or data.get("calibration_sha256") != source_hash
                or data.get("status") not in {"PASSED", "FAILED"}):
            raise ValueError("Invalid source trial review")
        if data["status"] == "FAILED":
            raise ValueError("Do not reuse measurements from a profile that failed a reviewed fresh trial")
    if (old.get("format") not in {"eye-guard-calibration-v4", "eye-guard-calibration-v5"}
            or old.get("geometry_hashes") != geometry_hashes()
            or old.get("guard_version") != EyeClosureGuard.VERSION):
        raise ValueError("Unsupported source calibration or changed geometry")
    phases = {name: [] for name in PHASES}
    csv_path = source/"observations.csv"
    with csv_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["phase"] not in phases: raise ValueError("Unknown calibration phase")
            phases[row["phase"]].append({key: float(row[key]) if row.get(key) else None
                                        for key in ("elapsed_s", "ear", "left_ear", "right_ear", "yaw", "pitch")})
    report = analyze(phases, old["device_code"], old["condition"],
                     capture_completed=old["capture_completed"], profile_id=old["profile_id"],
                     camera=old["camera_index"], frame_size=old["frame_size"])
    report.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
                  release_status="DEVELOPMENT_REANALYSIS_FRESH_TRIAL_REQUIRED",
                  source_report_sha256=source_hash,
                  source_measurements_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                  source_format=old["format"], source_status=old["status"],
                  source_previously_reviewed=True, user_confirmed_closed_actions=bool(closed_actions_confirmed),
                  scope="Reanalysis of reviewed calibration; no independent final validation or fresh trial")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(csv_path, output/"observations.csv")
    (output/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--closed-actions-confirmed", action="store_true")
    args = parser.parse_args()
    report = reanalyze(args.source, args.output, closed_actions_confirmed=args.closed_actions_confirmed)
    print(json.dumps({"status": report["status"], "reason": report.get("reason"),
                      "candidate_threshold": report.get("candidate_threshold"),
                      "report": str(args.output/"report.json"), "fresh_camera_trial_required": True}))


if __name__ == "__main__": main()
