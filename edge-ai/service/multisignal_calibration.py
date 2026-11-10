"""Explicit per-operator/camera/condition profile for the optional v2 closure branch."""
import json
import hashlib
from pathlib import Path
import numpy as np

from ml.multisignal_v2_features import QUALITY_VERSION, finite
from service.eye_calibration import geometry_hashes, PHASES, phase_statistics, validation_statistics
from service.eye_closure_guard import EyeClosureGuard

FORMAT = "eye-guard-calibration-v5"
FIT_METHOD = "fit-median-midpoint-temporal-validation-v1"
PHASE_DURATIONS = dict(zip(PHASES, (8., 8., 30., 8.)))


def analyze(phases, device_code, condition, *, capture_completed, profile_id, camera, frame_size):
    report = dict(device_code=device_code, condition=condition, capture_completed=bool(capture_completed),
        geometry_hashes=geometry_hashes(), guard_version=EyeClosureGuard.VERSION,
        closed_seconds=1., recovery_seconds=1., max_gap_seconds=.5, threshold_applied=False,
        annotation_source="guided user actions; not model predictions",
        scope="One-session eye/head calibration; fresh acceptance required")
    report.update(format=FORMAT, profile_id=profile_id, camera_index=camera,
                  frame_size=list(frame_size) if frame_size else None, quality_version=QUALITY_VERSION,
                  fit_method=FIT_METHOD, phase_durations=PHASE_DURATIONS,
                  release_status="CALIBRATION_ONLY_FRESH_TRIAL_REQUIRED")
    # Natural blinks may occupy more than 10% of an open phase. Separate the
    # typical levels on FIT only, then validate sustained closure on all phases.
    # A reanalysis of previously reviewed phases is development evidence only.
    for key in ("fit", "validation", "candidate_threshold", "reason"):
        report.pop(key, None)
    report["status"] = "REJECTED"
    try:
        if not capture_completed or set(phases) != set(PHASES):
            raise ValueError("Complete all four phases")
        opened, closed = (phase_statistics(phases[key], PHASE_DURATIONS[key]) for key in ("open_fit", "closed_fit"))
        if opened["median"] - closed["median"] < max(.02, .1*opened["median"]):
            raise ValueError("Typical open and closed measurements do not separate")
        # Reject poor separation before fitting a threshold. The midpoint of
        # typical open/closed levels leaves room for noise on either side;
        # a threshold near the closed tail can restart a 1s timer repeatedly.
        # Repeated open/speech must still pass without false sustained closure.
        margin = opened["median"]-closed["p90"]
        if margin < max(.02, .1*opened["median"]):
            raise ValueError("Closed-eye tail is too close to typical open eyes")
        threshold = .5*(opened["median"] + closed["median"])
        report.update(fit={"open": opened, "closed": closed}, candidate_threshold=threshold)
        checks = {key: validation_statistics(phases[key], threshold, PHASE_DURATIONS[key]) for key in PHASES}
        report["temporal_checks"] = checks
        if any(checks[key]["guard_activated"] for key in ("open_fit", "open_validation")):
            raise ValueError("False sustained closure during open-eye actions")
        if any(not checks[key]["guard_activated"] or checks[key]["measured_closed_fraction"] < .9
               for key in ("closed_fit", "closed_validation")):
            raise ValueError("Sustained closed-eye actions not reliably measured")
        # The neutral reference is collected only while explicitly looking
        # forward, never during an idle camera window or an unknown initial pose.
        neutral = phases["open_fit"]
        head = {}
        for axis, max_spread in (("yaw", .06), ("pitch", .03)):
            values = [r.get(axis) for r in neutral if finite(r.get(axis))]
            if len(values) < .8*len(neutral) or np.percentile(values, 90)-np.percentile(values, 10) > max_spread:
                raise ValueError("Look-forward reference is missing or unstable")
            head[axis] = float(np.median(values))
        report["head_baseline"] = head
        if threshold > checks["open_validation"]["median"]-max(.02, .1*checks["open_validation"]["median"]):
            raise ValueError("Threshold is too close to the repeated open-eye level")
        report["status"] = "READY_FOR_TRIAL"
    except (ValueError, TypeError) as error:
        report["reason"] = str(error)
    if (not isinstance(profile_id, str) or not profile_id.strip() or len(profile_id) > 80
            or condition not in {"glasses", "no-glasses"} or camera < 0
            or not frame_size or len(frame_size) != 2 or min(frame_size) <= 0):
        report.update(status="REJECTED", reason="Explicit operator, camera, resolution and condition required")
    return report


def load_profile(path, *, device_code, profile_id, camera, condition):
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError("Calibration report is too large")
    report = json.loads(path.read_text(encoding="utf-8"))
    expected = {"format": FORMAT, "status": "READY_FOR_TRIAL", "capture_completed": True,
                "device_code": device_code, "profile_id": profile_id, "condition": condition,
                "camera_index": camera, "quality_version": QUALITY_VERSION,
                "fit_method": FIT_METHOD,
                "phase_durations": PHASE_DURATIONS,
                "geometry_hashes": geometry_hashes(), "guard_version": EyeClosureGuard.VERSION,
                "closed_seconds": 1., "recovery_seconds": 1., "max_gap_seconds": .5}
    if any(report.get(k) != v for k, v in expected.items()) or not profile_id:
        raise ValueError("Rejected, old or mismatched operator/camera/condition calibration")
    if not finite(report.get("candidate_threshold"), .001, .8):
        raise ValueError("Invalid calibrated EAR threshold")
    size = report.get("frame_size")
    if not isinstance(size, list) or len(size) != 2 or not all(type(v) is int and v > 0 for v in size):
        raise ValueError("Calibration resolution missing")
    if not isinstance(report.get("head_baseline"), dict) or not all(finite(report["head_baseline"].get(k)) for k in ("yaw", "pitch")):
        raise ValueError("Explicit look-forward reference missing")
    report["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    review_path = path.with_name("fresh-trial-review.json")
    if review_path.exists():
        if review_path.stat().st_size > 65536:
            raise ValueError("Calibration trial review is too large")
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if (review.get("format") != "eye-guard-trial-review-v1"
                or review.get("calibration_sha256") != report["_sha256"]
                or review.get("status") not in {"PASSED", "FAILED"}):
            raise ValueError("Invalid or mismatched fresh-trial review")
        if review["status"] == "FAILED":
            raise ValueError("Calibration failed a reviewed fresh trial; do not reuse this eye guard. "
                             "Inspect fresh-trial-review.json; a new calibration and fresh trial are required.")
    return report


def head_tracker_for_profile(profile, **settings):
    from head_pose import HeadPoseTracker
    tracker = HeadPoseTracker(**settings)
    tracker.yaw_baseline = profile["head_baseline"]["yaw"]
    tracker.pitch_baseline = profile["head_baseline"]["pitch"]
    tracker.calibrating = False
    return tracker
