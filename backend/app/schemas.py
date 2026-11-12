from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class AdmissionInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=125)


class TemperatureInput(BaseModel):
    value: float = Field(ge=0, le=120)
    unit: str = Field(pattern="^[CF]$")
    measured_at: datetime
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_unit_range(self):
        minimum, maximum = (30, 45) if self.unit == "C" else (86, 113)
        if not minimum <= self.value <= maximum:
            raise ValueError(f"Temperature in {self.unit} must be between {minimum} and {maximum}")
        return self


class TemperatureCorrectionInput(BaseModel):
    value: float = Field(ge=0, le=120)
    unit: str = Field(pattern="^[CF]$")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def require_nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A correction reason is required")
        return value.strip()

    @model_validator(mode="after")
    def validate_unit_range(self):
        minimum, maximum = (30, 45) if self.unit == "C" else (86, 113)
        if not minimum <= self.value <= maximum:
            raise ValueError(f"Temperature in {self.unit} must be between {minimum} and {maximum}")
        return self


class VisitInput(BaseModel):
    notes: str = Field(default="", max_length=2000)
    visited_at: datetime | None = None
    urgent_reason: str = Field(default="", max_length=500)


class DischargeInput(BaseModel):
    notes: str = Field(default="", max_length=1000)


class OutcomeInput(BaseModel):
    notes: str = Field(default="", max_length=1000)


class ReviewInput(BaseModel):
    notes: str = Field(default="", max_length=1000)


class IntakeInput(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    age: int | None = Field(default=None, ge=0, le=125)
    details: str = Field(default="", max_length=2000)


class IntakeCompletionInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=125)
    details: str = Field(default="", max_length=2000)


class AssistantInput(BaseModel):
    question: str = Field(default="", max_length=2000)


class AssistantReviewInput(BaseModel):
    review_note: str = Field(min_length=1, max_length=1000)


class SettingsInput(BaseModel):
    fever_threshold_c: float = Field(ge=35, le=42)
    facility_timezone: str = Field(min_length=1, max_length=80)
    discharge_requires_doctor_review: bool
