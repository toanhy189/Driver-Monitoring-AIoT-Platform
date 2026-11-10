"""Local eye-guard calibration with separate fitting and validation actions.

This checks measured eye closure on one camera session, not drowsiness accuracy.
It never changes RF preprocessing, saves images, or activates settings.
"""

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from service.eye_closure_guard import EyeClosureGuard

FORMAT = "eye-guard-calibration-v2"
PHASES = ("open_fit", "closed_fit", "open_validation", "closed_validation")
DURATION = 5.0
MIN_COVERAGE = .8
MAX_GAP = .5
ROOT = Path(__file__).resolve().parents[1]


def geometry_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("eye.py", "geometry.py")}


def phase_statistics(rows, duration=DURATION):
    if len(rows) < 2:
        raise ValueError("Not enough observations")
    times = [float(r["elapsed_s"]) for r in rows]
    if (not all(math.isfinite(t) and 0 <= t <= duration for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError("Invalid phase timestamps")
    values, weights = [], []
    for first, second in zip(rows, rows[1:]):
        dt = second["elapsed_s"] - first["elapsed_s"]
        if all(r.get("ear") is not None and math.isfinite(r["ear"]) and r["ear"] >= 0
               for r in (first, second)) and dt <= MAX_GAP:
            values.append(float(first["ear"]))
            weights.append(float(dt))
    coverage = sum(weights) / duration
    if coverage < MIN_COVERAGE:
        raise ValueError("Insufficient observed coverage")
    order = np.argsort(values)
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    cumulative = np.cumsum(weights)
    def quantile(q):
        return float(values[min(np.searchsorted(cumulative, q*cumulative[-1]), len(values)-1)])
    return {"coverage": coverage, "valid_intervals": len(weights),
            "p10": quantile(.1), "median": quantile(.5), "p90": quantile(.9)}


def validation_statistics(rows, threshold, duration=DURATION):
    summary = phase_statistics(rows, duration)
    guard = EyeClosureGuard(ear_threshold=threshold)
    active = False
    wrong_time = total = 0.0
    for index, row in enumerate(rows):
        active |= guard.update(row["elapsed_s"], row.get("ear"))
        if index == 0:
            continue
        previous = rows[index-1]
        dt = row["elapsed_s"] - previous["elapsed_s"]
        a, b = previous.get("ear"), row.get("ear")
        if (a is not None and b is not None and math.isfinite(a) and math.isfinite(b)
                and a >= 0 and b >= 0 and dt <= MAX_GAP):
            total += dt
            wrong_time += dt * (a < threshold)
    return {**summary, "measured_closed_fraction": wrong_time / total,
            "guard_activated": bool(active)}


def analyze(phases, device_code, condition, *, capture_completed):
    report = {"format": FORMAT, "status": "REJECTED", "device_code": device_code,
              "condition": condition, "annotation_source": "guided user actions; not model predictions",
              "geometry_hashes": geometry_hashes(), "guard_version": EyeClosureGuard.VERSION,
              "closed_seconds": 1.0, "recovery_seconds": 1.0, "max_gap_seconds": MAX_GAP,
              "scope": "One-session eye-closure calibration; not drowsiness or new-person acceptance",
              "threshold_applied": False, "capture_completed": bool(capture_completed)}
    try:
        if not capture_completed or set(phases) != set(PHASES):
            raise ValueError("Complete all four phases, including separate validation")
        opened = phase_statistics(phases["open_fit"])
        closed = phase_statistics(phases["closed_fit"])
        report["fit"] = {"open": opened, "closed": closed}
        gap = opened["p10"] - closed["p90"]
        required = max(.02, .1 * opened["median"])
        if gap < required:
            raise ValueError("Open and closed measurements do not separate reliably")
        # Only fitting phases determine the candidate. Never tune it to validation.
        threshold = (opened["p10"] + closed["p90"]) / 2
        report["candidate_threshold"] = threshold
        open_check = validation_statistics(phases["open_validation"], threshold)
        closed_check = validation_statistics(phases["closed_validation"], threshold)
        report["validation"] = {"open": open_check, "closed": closed_check}
        # The instructed open action allows natural blinks. Brief closures are
        # not false prolonged-closure alarms; validate the actual temporal guard.
        if open_check["guard_activated"]:
            raise ValueError("False eye-closure evidence during open-eye validation")
        if not closed_check["guard_activated"] or closed_check["measured_closed_fraction"] < .9:
            raise ValueError("Closed-eye validation not reliably observed")
        report["status"] = "READY_FOR_TRIAL"
    except (ValueError, TypeError) as exc:
        report["reason"] = str(exc)
    return report


def load_threshold(path, device_code):
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError("Calibration report is too large")
    report = json.loads(path.read_text(encoding="utf-8"))
    if (report.get("format") != FORMAT or report.get("status") != "READY_FOR_TRIAL"
            or report.get("capture_completed") is not True
            or report.get("device_code") != device_code
            or report.get("geometry_hashes") != geometry_hashes()
            or report.get("guard_version") != EyeClosureGuard.VERSION
            or (report.get("closed_seconds"), report.get("recovery_seconds"), report.get("max_gap_seconds"))
                != (1.0, 1.0, MAX_GAP)):
        raise ValueError("Calibration is rejected, incompatible or belongs to another device")
    threshold = float(report["candidate_threshold"])
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("Invalid calibrated threshold")
    return threshold
