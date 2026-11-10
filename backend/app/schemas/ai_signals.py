"""Optional versioned measurements; these never change rule policy or device commands."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictBool, TypeAdapter, model_validator


class AiSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["eye-mouth-v1"]
    mar: FiniteFloat | None = Field(default=None, ge=0, le=2)
    yawn_probability: FiniteFloat | None = Field(default=None, ge=0, le=1)
    eye_sleepy_probability: FiniteFloat | None = Field(default=None, ge=0, le=1)
    fusion_score: FiniteFloat | None = Field(default=None, ge=0, le=1)
    mouth_state: Literal["NORMAL", "YAWN", "TALKING_LAUGHING", "UNKNOWN"] = "UNKNOWN"
    eye_state: Literal["NORMAL", "SLEEPY", "UNKNOWN"] = "UNKNOWN"
    eyes_available: StrictBool = False
    mouth_available: StrictBool = False
    experimental: StrictBool = True

    @model_validator(mode="after")
    def missing_is_unknown(self):
        if not self.eyes_available and (self.eye_state != "UNKNOWN" or self.eye_sleepy_probability is not None):
            raise ValueError("Unavailable eyes must remain UNKNOWN with no eye score")
        if not self.mouth_available and (self.mouth_state != "UNKNOWN" or self.yawn_probability is not None
                                        or (self.schema_version == "eye-mouth-v1" and self.mar is not None)):
            raise ValueError("Unavailable mouth must remain UNKNOWN with no mouth measurements")
        return self


Quality = Literal["VALID", "NO_CROP", "NO_FACE", "BLANK", "LOW_CONTRAST", "SATURATED"]
CropReason = Literal["VALID", "NO_FACE", "INVALID_GEOMETRY", "SMALL_REGION", "OUTSIDE_FRAME", "EMPTY_REGION", "BLANK"]
DecisionReason = Literal["WARMUP", "INSUFFICIENT_COVERAGE", "NO_FACE", "FRAME_GAP", "INFERENCE_FAILED",
                         "EYE_CLOSURE_RISK", "RF_POSITIVE", "RF_NEGATIVE", "HEAD_DEVIATION",
                         "HEAD_CALIBRATING", "HEAD_UNAVAILABLE", "INSUFFICIENT_SUPPORT", "HEAD_EYE_CLOSURE_RISK", "HEAD_DOWN_RISK"]


class HeadMotion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["head-motion-v1"]
    mode: Literal["OBSERVE_ONLY"]
    available: StrictBool
    calibrated: StrictBool
    state: Literal["UNAVAILABLE", "CALIBRATING", "REACQUIRING", "OUT_OF_RANGE", "NEUTRAL", "MOVING", "LOWERED", "NOD_DETECTED", "REPEATED_NODS"]
    pitch_deg: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    yaw_deg: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    roll_deg: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    nod_count: int = Field(ge=0, le=100, strict=True)
    repeated_nods: StrictBool
    eye_closure_supported: StrictBool

    @model_validator(mode="after")
    def coherent_observation(self):
        angles = (self.pitch_deg, self.yaw_deg, self.roll_deg)
        if self.available != (self.state != "UNAVAILABLE"):
            raise ValueError("Missing head motion must remain UNAVAILABLE")
        if self.state in {"UNAVAILABLE", "CALIBRATING"}:
            if any(v is not None for v in angles) or self.nod_count:
                raise ValueError("Unavailable or uncalibrated head cannot retain angles or nods")
        elif not self.calibrated or any(v is None for v in angles):
            raise ValueError("Measured head motion requires calibrated current angles")
        if self.state == "CALIBRATING" and self.calibrated:
            raise ValueError("Calibration cannot be complete while calibrating")
        if self.state in {"OUT_OF_RANGE", "REACQUIRING"} and self.nod_count:
            raise ValueError("Unsupported pose must interrupt nod evidence")
        if self.repeated_nods != (self.nod_count >= 2):
            raise ValueError("Repeated nods must match the window count")
        if self.state == "REPEATED_NODS" and not self.repeated_nods:
            raise ValueError("Repeated nod state requires two complete cycles")
        if self.eye_closure_supported and not self.repeated_nods:
            raise ValueError("Eye support requires repeated nod evidence")
        return self


class HeadEyeFusionSignals(BaseModel):
    # Read compatibility for stored experimental telemetry; current AI no longer emits this branch.
    model_config = ConfigDict(extra="forbid")
    version: Literal["pose-calibrated-head-eye-v1"]
    mode: Literal["PRIVATE_PREVIEW", "ENABLED"]
    state: Literal["UNAVAILABLE", "OPEN", "CLOSING", "CLOSED_RISK", "RECOVERING"]
    ear_threshold: FiniteFloat | None = Field(default=None, gt=0, lt=.8)
    risk_candidate: StrictBool
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def coherent_risk(self):
        if (self.state == "UNAVAILABLE") != (self.ear_threshold is None):
            raise ValueError("Pose eye threshold requires a current usable observation")
        if self.risk_candidate and self.state not in {"CLOSED_RISK", "RECOVERING"}:
            raise ValueError("Pose eye risk requires a prolonged closure decision")
        return self


class HeadDownPolicySignals(BaseModel):
    model_config=ConfigDict(extra="forbid")
    version: Literal["sustained-head-down-v1"]
    state: Literal["UNAVAILABLE","CALIBRATING","NORMAL","LOWERED","DOWN_RISK","RECOVERING"]
    risk_candidate: StrictBool
    observed_down_seconds: FiniteFloat=Field(ge=0)
    enter_pitch_deg: Literal[12.0]
    min_seconds: Literal[3.0]

    @model_validator(mode="after")
    def consistent_duration(self):
        if self.risk_candidate != (self.state in {"DOWN_RISK","RECOVERING"}):
            raise ValueError("Posture risk must match its state")
        if self.risk_candidate and self.observed_down_seconds<3.:
            raise ValueError("Posture warning requires three seconds of observation")
        if self.state in {"UNAVAILABLE","CALIBRATING","NORMAL"} and self.observed_down_seconds!=0:
            raise ValueError("Missing or neutral posture cannot retain downward duration")
        return self


class AiSignalsV2(AiSignals):
    schema_version: Literal["eye-mouth-v2"]
    quality_version: Literal["region-technical-quality-v1"]
    ear_available: StrictBool
    eye_confidence: FiniteFloat | None = Field(default=None, ge=0, le=1)
    mouth_confidence: FiniteFloat | None = Field(default=None, ge=0, le=1)
    eye_quality: Quality
    mouth_quality: Quality
    eye_crop_reason: CropReason | None = None
    mouth_crop_reason: CropReason | None = None
    decision_reason: DecisionReason
    sample_age_ms: FiniteFloat | None = Field(default=None, ge=0, le=200.001)
    eye_closure_state: Literal["DISABLED", "UNAVAILABLE", "OPEN", "CLOSING", "CLOSED_RISK", "RECOVERING"]
    calibration_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    head_motion: HeadMotion | None = None
    head_eye_fusion: HeadEyeFusionSignals | None = None
    head_down_policy: HeadDownPolicySignals | None = None

    @model_validator(mode="after")
    def current_quality(self):
        for region in ("eye", "mouth"):
            reason = getattr(self, f"{region}_crop_reason")
            if reason not in {None, "VALID"} and getattr(self, f"{region}_quality") == "VALID":
                raise ValueError("A failed crop cannot carry usable image quality")
        if self.eye_quality != "VALID" and (self.eyes_available or self.ear_available or self.eye_confidence is not None):
            raise ValueError("Unusable eye images cannot carry current eye evidence")
        if self.mouth_quality != "VALID" and (self.mouth_available or self.mar is not None or self.mouth_confidence is not None):
            raise ValueError("Unusable mouth images cannot carry current mouth evidence")
        if self.eyes_available and (self.eye_sleepy_probability is None or self.eye_confidence is None):
            raise ValueError("Available eye probabilities require their classifier confidence")
        if self.mouth_available and (self.yawn_probability is None or self.mouth_confidence is None):
            raise ValueError("Available mouth probabilities require their classifier confidence")
        if self.eye_closure_state in {"OPEN", "CLOSING", "CLOSED_RISK", "RECOVERING"} and not self.ear_available:
            raise ValueError("Closure evidence requires current independent geometry")
        if self.head_motion and self.head_motion.eye_closure_supported and self.eye_closure_state != "CLOSED_RISK":
            raise ValueError("Head/eye corroboration requires current closed-eye risk")
        if self.head_eye_fusion and self.head_eye_fusion.state != "UNAVAILABLE":
            if (not self.ear_available or not self.calibration_id or not self.head_motion
                    or not self.head_motion.available or not self.head_motion.calibrated
                    or self.head_motion.state in {"OUT_OF_RANGE", "REACQUIRING", "CALIBRATING", "UNAVAILABLE"}):
                raise ValueError("Pose eye fusion requires current eyes and calibrated head observation")
        if self.decision_reason == "HEAD_EYE_CLOSURE_RISK" and not (self.head_eye_fusion and self.head_eye_fusion.risk_candidate):
            raise ValueError("Head eye decision reason requires matching evidence")
        if self.head_down_policy and self.head_down_policy.state not in {"UNAVAILABLE","CALIBRATING"}:
            if not self.head_motion or not self.head_motion.available or not self.head_motion.calibrated or self.head_motion.state in {"UNAVAILABLE","CALIBRATING","OUT_OF_RANGE"}:
                raise ValueError("Posture policy requires current calibrated head angles")
            h=self.head_motion
            if abs(h.yaw_deg)>20. or abs(h.roll_deg)>15. or not -15.<=h.pitch_deg<=40.:
                raise ValueError("Posture observation is outside the supported angle range")
            if self.head_down_policy.state=="DOWN_RISK" and h.pitch_deg<8.:
                raise ValueError("Downward risk requires a currently lowered head")
        if self.decision_reason == "HEAD_DOWN_RISK" and not (self.head_down_policy and self.head_down_policy.risk_candidate):
            raise ValueError("Head down reason requires matching posture evidence")
        return self


AiSignalsPayload = Annotated[AiSignals | AiSignalsV2, Field(discriminator="schema_version")]
_adapter = TypeAdapter(AiSignalsPayload)


def parse_ai_signals(value):
    return _adapter.validate_python(value)
