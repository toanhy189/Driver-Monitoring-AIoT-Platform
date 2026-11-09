"""Optional versioned measurements; these never change rule policy or device commands."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictBool, model_validator


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
        if not self.mouth_available and (self.mouth_state != "UNKNOWN" or self.yawn_probability is not None or self.mar is not None):
            raise ValueError("Unavailable mouth must remain UNKNOWN with no mouth measurements")
        return self
