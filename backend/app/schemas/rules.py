from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, StrictInt, field_validator, model_validator


class AiEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=80, validation_alias=AliasChoices("event_id", "message_id"))
    device_id: str = Field(min_length=1, max_length=100, validation_alias=AliasChoices("device_id", "device_code"))
    event_type: Literal["DROWSY_THRESHOLD_REACHED", "DISTRACTED_THRESHOLD_REACHED", "STATE_CHANGED", "SESSION_ENDED"]
    timestamp: datetime
    model_version: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=30)
    final_state: Literal["ATTENTIVE", "DISTRACTED", "DROWSY", "UNKNOWN"] | None = None
    state_duration_ms: StrictInt | None = Field(default=None, ge=0, le=86400000)

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include UTC offset")
        return value

    @model_validator(mode="after")
    def threshold_duration_required(self):
        if self.event_type.endswith("_THRESHOLD_REACHED") and self.state_duration_ms is None:
            raise ValueError("state_duration_ms is required")
        if self.event_type.endswith("_THRESHOLD_REACHED") and self.state != self.event_type.removesuffix("_THRESHOLD_REACHED"):
            raise ValueError("threshold event must match its state")
        return self


class RuleLevel(BaseModel):
    threshold_ms: StrictInt = Field(ge=1, le=86400000)
    duration_ms: StrictInt = Field(ge=1, le=10000)
    outputs: list[Literal["led", "buzzer", "motor"]] = Field(
        default_factory=lambda: ["led", "buzzer", "motor"], min_length=1, max_length=3)

    @field_validator("outputs")
    @classmethod
    def unique_outputs(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("outputs must not contain duplicates")
        return value


class RulePolicy(BaseModel):
    levels: dict[Literal["1", "2", "3"], RuleLevel] = Field(default_factory=lambda: {
        "1": RuleLevel(threshold_ms=3000, duration_ms=1000),
        "2": RuleLevel(threshold_ms=6000, duration_ms=2000),
        "3": RuleLevel(threshold_ms=10000, duration_ms=3000),
    })
    cooldown_seconds: StrictInt = Field(default=30, ge=0, le=3600)
    max_event_age_seconds: StrictInt = Field(default=60, ge=1, le=86400)

    @model_validator(mode="after")
    def ordered_levels(self):
        if set(self.levels) != {"1", "2", "3"}:
            raise ValueError("All three severity levels are required")
        thresholds = [self.levels[str(level)].threshold_ms for level in (1, 2, 3)]
        if not thresholds[0] < thresholds[1] < thresholds[2]:
            raise ValueError("severity thresholds must increase")
        return self


class RuleBindingRequest(BaseModel):
    target_device_id: StrictInt = Field(gt=0)
    enabled: bool = False
    policy: RulePolicy = Field(default_factory=RulePolicy)
