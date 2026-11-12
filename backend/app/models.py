from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    full_name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    admissions: Mapped[list["Admission"]] = relationship(back_populates="patient")


class Bed(Base):
    __tablename__ = "beds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bed_code: Mapped[str] = mapped_column(String(16), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Admission(Base):
    __tablename__ = "admissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    bed_id: Mapped[str] = mapped_column(ForeignKey("beds.id"), index=True)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    closed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    patient: Mapped[Patient] = relationship(back_populates="admissions")
    bed: Mapped[Bed] = relationship()


Index(
    "uq_admission_active_bed",
    Admission.bed_id,
    unique=True,
    sqlite_where=Admission.status == "active",
)
Index(
    "uq_admission_active_patient",
    Admission.patient_id,
    unique=True,
    sqlite_where=Admission.status == "active",
)


class TemperatureReading(Base):
    __tablename__ = "temperature_readings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    admission_id: Mapped[str] = mapped_column(ForeignKey("admissions.id"), index=True)
    value_c: Mapped[float] = mapped_column(Float)
    unit_entered: Mapped[str] = mapped_column(String(1))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="accepted")
    correction_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("temperature_readings.id"),
        nullable=True,
    )
    correction_reason: Mapped[str] = mapped_column(Text, default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


Index(
    "uq_temperature_daily",
    TemperatureReading.admission_id,
    TemperatureReading.local_date,
    unique=True,
    sqlite_where=TemperatureReading.status == "accepted",
)


class DoctorVisit(Base):
    __tablename__ = "doctor_visits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    admission_id: Mapped[str] = mapped_column(ForeignKey("admissions.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    urgent_reason: Mapped[str] = mapped_column(Text, default="")


Index("uq_visit_daily", DoctorVisit.admission_id, DoctorVisit.local_date, unique=True)


class DischargeReview(Base):
    __tablename__ = "discharge_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    admission_id: Mapped[str] = mapped_column(ForeignKey("admissions.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    notes: Mapped[str] = mapped_column(Text, default="")


class Discharge(Base):
    __tablename__ = "discharges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    admission_id: Mapped[str] = mapped_column(ForeignKey("admissions.id"), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    discharged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finalized_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str] = mapped_column(Text, default="")


class PatientOutcome(Base):
    __tablename__ = "patient_outcomes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    admission_id: Mapped[str] = mapped_column(ForeignKey("admissions.id"), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    outcome_type: Mapped[str] = mapped_column(String(24))
    outcome_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str] = mapped_column(Text, default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IntakeRequest(Base):
    __tablename__ = "intake_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="needs_review", index=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AssistantRequest(Base):
    __tablename__ = "assistant_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    question: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="needs_review", index=True)
    answer: Mapped[str] = mapped_column(Text, default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
