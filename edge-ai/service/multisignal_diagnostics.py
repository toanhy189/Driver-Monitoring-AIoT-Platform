"""Explain existing decisions for a private trial; never alter driver states."""
def decision_reason(model, face_detected, pose_status, raw_state, *, policy_gap=False):
    if policy_gap:
        return "FRAME_GAP"
    if getattr(model, "failed", False):
        return "INFERENCE_FAILED"
    if not face_detected:
        return "NO_FACE"
    signals = model.telemetry_signals()
    if signals.get("schema_version") == "eye-mouth-v2":
        return signals["decision_reason"]
    if raw_state == "DROWSY":
        return "RF_POSITIVE_WITH_CURRENT_SUPPORT"
    if raw_state == "DISTRACTED":
        return "HEAD_DEVIATION_CONFIRMED"
    if raw_state == "ATTENTIVE":
        return "RF_NEGATIVE_EYES_AND_HEAD_VALID"
    if signals.get("fusion_score") is None:
        return "FUSION_" + getattr(model.window, "last_quality_reason", "NOT_READY")
    if not signals.get("eyes_available"):
        diagnostics = getattr(model, "region_diagnostics", {})
        return "EYES_LOW_CONFIDENCE" if diagnostics.get("eyes_crop_available") else "EYES_CROP_UNAVAILABLE"
    if not pose_status or not pose_status.get("valid"):
        return "HEAD_UNAVAILABLE"
    if pose_status.get("calibrating", True):
        return "HEAD_CALIBRATING"
    return "INSUFFICIENT_CURRENT_SUPPORT"
