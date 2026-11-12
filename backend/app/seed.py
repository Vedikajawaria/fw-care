from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.domain.eligibility import facility_today
from app.models import (
    Admission,
    Bed,
    DoctorVisit,
    Patient,
    PatientOutcome,
    Setting,
    TemperatureReading,
    User,
)


def seed_demo_data(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        return

    users = [
        User(
            full_name="Morgan Lee",
            username="admin",
            password_hash=hash_password("Demo123!"),
            role="admin",
        ),
        User(
            full_name="Avery Patel",
            username="nurse",
            password_hash=hash_password("Demo123!"),
            role="nurse",
        ),
        User(
            full_name="Jordan Kim",
            username="doctor",
            password_hash=hash_password("Demo123!"),
            role="doctor",
        ),
    ]
    db.add_all(users)
    db.flush()
    admin, nurse, doctor = users
    beds = [Bed(bed_code=f"A-{number:02d}") for number in range(1, 75)]
    db.add_all(beds)
    db.add_all(
        [
            Setting(key="fever_threshold_c", value="38.0"),
            Setting(key="facility_timezone", value="Asia/Kolkata"),
            Setting(key="discharge_requires_doctor_review", value="true"),
            Setting(key="facility_capacity", value="74"),
        ]
    )
    db.flush()

    tz_name = "Asia/Kolkata"
    today = facility_today(tz_name)
    timezone_info = ZoneInfo(tz_name)
    admissions: list[Admission] = []
    for number in range(72):
        patient = Patient(
            patient_code=f"FW-{number + 1:04d}",
            full_name=f"Demo Patient {number + 1:02d}",
            age=19 + number % 58,
        )
        db.add(patient)
        db.flush()
        admitted_local = datetime.combine(today - timedelta(days=10), time(9), timezone_info)
        admission = Admission(
            patient_id=patient.id,
            bed_id=beds[number].id,
            admitted_at=admitted_local.astimezone(UTC),
            status="active",
            created_by=admin.id,
        )
        db.add(admission)
        db.flush()
        admissions.append(admission)

        if number == 0:
            for offset in range(1, 4):
                local_measured = datetime.combine(today - timedelta(days=offset), time(10), timezone_info)
                db.add(
                    TemperatureReading(
                        patient_id=patient.id,
                        admission_id=admission.id,
                        value_c=36.8,
                        unit_entered="C",
                        measured_at=local_measured.astimezone(UTC),
                        local_date=today - timedelta(days=offset),
                        recorded_by=nurse.id,
                        note="Synthetic demo reading",
                    )
                )
        elif number % 3 == 0:
            local_measured = datetime.combine(today, time(9), timezone_info)
            db.add(
                TemperatureReading(
                    patient_id=patient.id,
                    admission_id=admission.id,
                    value_c=37.2 + (number % 5) / 10,
                    unit_entered="C",
                    measured_at=local_measured.astimezone(UTC),
                    local_date=today,
                    recorded_by=nurse.id,
                    note="Synthetic demo reading",
                )
            )
        if number % 4 == 0:
            db.add(
                DoctorVisit(
                    patient_id=patient.id,
                    admission_id=admission.id,
                    doctor_id=doctor.id,
                    visited_at=datetime.now(UTC),
                    local_date=today,
                    notes="Synthetic demo visit",
                )
            )

    for offset, outcome in enumerate(("discharged_alive", "deceased"), start=1):
        patient = Patient(
            patient_code=f"FW-H{offset:03d}",
            full_name=f"Historical Demo Patient {offset}",
            age=34 + offset,
        )
        db.add(patient)
        db.flush()
        historical = Admission(
            patient_id=patient.id,
            bed_id=beds[71 + offset].id,
            admitted_at=datetime.now(UTC) - timedelta(days=20),
            discharged_at=datetime.now(UTC) - timedelta(days=8),
            status="closed",
            created_by=admin.id,
            closed_by=admin.id,
        )
        db.add(historical)
        db.flush()
        db.add(
            PatientOutcome(
                admission_id=historical.id,
                patient_id=patient.id,
                outcome_type=outcome,
                outcome_at=historical.discharged_at,
                recorded_by=admin.id,
                notes="Synthetic demo outcome",
            )
        )

    db.commit()
