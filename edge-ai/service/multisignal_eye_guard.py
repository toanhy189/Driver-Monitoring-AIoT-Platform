"""Restore the legacy closure branch only for an explicitly unglassed trial.

The fixed threshold is a demo fallback, not a personal calibration or proof of
visibility through glasses. Profiles still pass the separate strict loader.
"""
import hashlib
import json

from service.eye_closure_guard import EyeClosureGuard

RULE_VERSION = "current-frontal-ear-condition-v1"
NO_GLASSES_EAR_THRESHOLD = .20


def build_eye_guard(condition, profile=None):
    if condition not in (None, "glasses", "no-glasses"):
        raise ValueError("Explicit glasses or no-glasses condition required")
    source = ("CALIBRATED_PROFILE" if profile else
              "NO_GLASSES_DEFAULT" if condition == "no-glasses" else "DISABLED")
    guard = (EyeClosureGuard(profile["candidate_threshold"] if profile else NO_GLASSES_EAR_THRESHOLD)
             if source != "DISABLED" else None)
    metadata = {"rule_version": RULE_VERSION, "condition": condition, "source": source,
                "enabled": guard is not None, "calibrated": profile is not None,
                "profile_sha256": profile.get("_sha256") if profile else None,
                "guard_version": EyeClosureGuard.VERSION,
                "ear_threshold": guard.ear_threshold if guard else None,
                "closed_seconds": guard.closed_seconds if guard else None,
                "recovery_seconds": guard.recovery_seconds if guard else None,
                "max_gap_seconds": guard.max_gap_seconds if guard else None}
    return guard, metadata


def runtime_version(base_version, metadata):
    if not metadata["enabled"]:
        return base_version
    identity = {"base_model_version": base_version, "eye_guard": metadata}
    return "eye-mouth-v2-guard-" + hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def current_guard_ear(ear, head):
    """EAR has already passed current-image admission; pose must also be current."""
    frontal = bool(head and head.get("valid") and not head.get("calibrating", True)
                   and not head.get("is_deviated") and not head.get("is_distracted"))
    return ear if frontal else None
