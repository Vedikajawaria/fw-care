from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.eligibility import evaluate_eligibility, facility_today
from app.models import (
    Admission,
    AuditEvent,
    Bed,
    DoctorVisit,
    Patient,
    Setting,
    TemperatureReading,
    User,
)


def setting(db: Session, key: str, default: str) -> str:
    row = db.get(Setting, key)
    return row.value if row else default


def record_audit(db: Session, actor: User, action: str, entity_type: str, entity_id: str, detail: str = ""):
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )
    )


def active_admission(db: Session, patient_id: str) -> Admission | None:
    return db.scalar(select(Admission).where(Admission.patient_id == patient_id, Admission.status == "active"))


def patient_summary(db: Session, patient: Patient, today: date, tz_name: str) -> dict:
    admission = active_admission(db, patient.id)
    bed_code = None
    if admission:
        bed = db.get(Bed, admission.bed_id)
        if bed is None:
            raise RuntimeError("An active admission references a missing bed")
        bed_code = bed.bed_code
    readings = db.scalars(
        select(TemperatureReading)
        .where(
            TemperatureReading.patient_id == patient.id,
            TemperatureReading.status == "accepted",
        )
        .order_by(TemperatureReading.measured_at.desc(), TemperatureReading.recorded_at.desc())
    ).all()
    visits = db.scalars(select(DoctorVisit).where(DoctorVisit.patient_id == patient.id).order_by(DoctorVisit.visited_at.desc())).all()
    threshold = float(setting(db, "fever_threshold_c", "38.0"))
    daily = [r for r in readings if r.local_date == today and r.status == "accepted"]
    yesterday = today - timedelta(days=1)
    yesterday_readings = [r for r in readings if r.local_date == yesterday and r.status == "accepted"]
    admitted_today = admission is not None and local_date_for(admission.admitted_at, tz_name) == today
    temp_status = "recorded" if daily else "missed yesterday" if admission and not admitted_today and not yesterday_readings else "pending"
    admitted_date = local_date_for(admission.admitted_at, tz_name) if admission else today
    eligibility_readings = [r for r in readings if r.local_date >= admitted_date]
    eligible = evaluate_eligibility(eligibility_readings, threshold, tz_name, today)
    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "full_name": patient.full_name,
        "age": patient.age,
        "admission_id": admission.id if admission else None,
        "admitted_at": admission.admitted_at.isoformat() if admission else None,
        "bed_code": bed_code,
        "status": admission.status if admission else "discharged",
        "temperature_status": temp_status,
        "latest_temperature_id": readings[0].id if readings else None,
        "latest_temperature_c": readings[0].value_c if readings else None,
        "doctor_visit_status": "recorded" if any(v.local_date == today for v in visits) else "pending",
        "eligible": eligible["eligible"],
        "temperature_count": len(readings),
    }


def eligibility_for_patient(db: Session, patient_id: str) -> dict:
    timezone_name = setting(db, "facility_timezone", "Asia/Kolkata")
    today = facility_today(timezone_name)
    threshold = float(setting(db, "fever_threshold_c", "38.0"))
    admission = active_admission(db, patient_id)
    readings = db.scalars(
        select(TemperatureReading)
        .where(
            TemperatureReading.patient_id == patient_id,
            TemperatureReading.status == "accepted",
        )
        .order_by(TemperatureReading.local_date.desc())
    ).all()
    if admission:
        admitted_date = local_date_for(admission.admitted_at, timezone_name)
        readings = [reading for reading in readings if reading.local_date >= admitted_date]
    result = evaluate_eligibility(readings, threshold, timezone_name, today)
    result["threshold_c"] = threshold
    return result


def local_date_for(value: datetime, timezone_name: str) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(ZoneInfo(timezone_name)).date()
