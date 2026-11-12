import csv
import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.security import (
    create_csrf_token,
    current_user,
    require_csrf,
    require_role,
    verify_password,
)
from app.db.session import SessionLocal, get_db, init_db
from app.domain.eligibility import facility_today
from app.models import (
    Admission,
    AssistantRequest,
    Bed,
    Discharge,
    DischargeReview,
    DoctorVisit,
    IntakeRequest,
    Patient,
    PatientOutcome,
    Setting,
    TemperatureReading,
    User,
    new_id,
)
from app.schemas import (
    AdmissionInput,
    AssistantInput,
    AssistantReviewInput,
    DischargeInput,
    IntakeCompletionInput,
    IntakeInput,
    LoginInput,
    OutcomeInput,
    ReviewInput,
    SettingsInput,
    TemperatureCorrectionInput,
    TemperatureInput,
    VisitInput,
)
from app.seed import seed_demo_data
from app.services import (
    active_admission,
    eligibility_for_patient,
    local_date_for,
    patient_summary,
    record_audit,
    setting,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_demo_data(db)
    yield


app = FastAPI(title="FactWise Care", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    same_site="lax",
    https_only=settings.cookie_secure,
    max_age=12 * 60 * 60,
)


def signed_in(request: Request, db: Session = Depends(get_db)) -> User:
    return current_user(request, db)


def user_view(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "role": user.role,
    }


def user_name(db: Session, user_id: str) -> str:
    user = db.get(User, user_id)
    if user is None:
        raise RuntimeError("A workflow record references a missing user")
    return user.full_name


def admission_view(db: Session, admission: Admission) -> dict:
    return {
        "id": admission.id,
        "patient_id": admission.patient_id,
        "patient_name": admission.patient.full_name,
        "patient_code": admission.patient.patient_code,
        "age": admission.patient.age,
        "bed_code": admission.bed.bed_code,
        "admitted_at": admission.admitted_at.isoformat(),
        "status": admission.status,
    }


def active_patients(db: Session) -> list[Patient]:
    return list(db.scalars(select(Patient).join(Admission).where(Admission.status == "active").order_by(Patient.patient_code)).all())


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username or password is incorrect")
    request.session.clear()
    csrf_token = create_csrf_token()
    request.session.update({"user_id": user.id, "csrf_token": csrf_token})
    return {"user": user_view(user), "csrf_token": csrf_token}


@app.post("/api/v1/auth/logout")
def logout(request: Request, user: User = Depends(signed_in)):
    require_csrf(request)
    request.session.clear()
    return {"ok": True}


@app.get("/api/v1/auth/me")
def me(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        request.session.clear()
        return {"user": None, "csrf_token": None}
    return {"user": user_view(user), "csrf_token": request.session.get("csrf_token")}


@app.get("/api/v1/patients")
def list_patients(
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    today = facility_today(tz_name)
    return [patient_summary(db, patient, today, tz_name) for patient in active_patients(db)]


@app.get("/api/v1/patients/{patient_id}")
def get_patient(patient_id: str, user: User = Depends(signed_in), db: Session = Depends(get_db)):
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient was not found")
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    summary = patient_summary(db, patient, facility_today(tz_name), tz_name)
    readings = db.scalars(
        select(TemperatureReading).where(TemperatureReading.patient_id == patient_id).order_by(TemperatureReading.measured_at.desc())
    ).all()
    visits = db.scalars(select(DoctorVisit).where(DoctorVisit.patient_id == patient_id).order_by(DoctorVisit.visited_at.desc())).all()
    return {
        **summary,
        "temperatures": [
            {
                "id": row.id,
                "value_c": row.value_c,
                "unit_entered": row.unit_entered,
                "measured_at": row.measured_at.isoformat(),
                "local_date": row.local_date.isoformat(),
                "note": row.note,
                "recorded_by": user_name(db, row.recorded_by),
                "status": row.status,
                "correction_of_id": row.correction_of_id,
                "correction_reason": row.correction_reason,
                "recorded_at": row.recorded_at.isoformat(),
            }
            for row in readings
        ],
        "visits": [
            {
                "id": row.id,
                "visited_at": row.visited_at.isoformat(),
                "local_date": row.local_date.isoformat(),
                "notes": row.notes,
                "doctor": user_name(db, row.doctor_id),
                "urgent_reason": row.urgent_reason,
            }
            for row in visits
        ],
    }


@app.get("/api/v1/beds")
def list_beds(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    beds = db.scalars(select(Bed).order_by(Bed.bed_code)).all()
    active_by_bed = {admission.bed_id: admission for admission in db.scalars(select(Admission).where(Admission.status == "active")).all()}
    return [
        {
            "id": bed.id,
            "bed_code": bed.bed_code,
            "is_active": bed.is_active,
            "occupied": bed.id in active_by_bed,
            "patient_id": active_by_bed[bed.id].patient_id if bed.id in active_by_bed else None,
        }
        for bed in beds
    ]


@app.get("/api/v1/occupancy")
def occupancy(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    total = int(setting(db, "facility_capacity", "74"))
    occupied = db.scalar(select(func.count()).select_from(Admission).where(Admission.status == "active")) or 0
    return {"capacity": total, "occupied": occupied, "available": max(0, total - occupied)}


@app.post("/api/v1/admissions")
def admit(
    payload: AdmissionInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "admin")
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        capacity = int(setting(db, "facility_capacity", "74"))
        occupied = db.scalar(select(func.count()).select_from(Admission).where(Admission.status == "active")) or 0
        bed = db.scalar(
            select(Bed)
            .where(
                Bed.is_active.is_(True),
                ~Bed.id.in_(select(Admission.bed_id).where(Admission.status == "active")),
            )
            .order_by(Bed.bed_code)
            .limit(1)
        )
        if occupied >= capacity or not bed:
            raise HTTPException(status_code=409, detail=f"Facility capacity reached ({capacity} beds)")
        duplicate = db.scalar(
            select(Patient)
            .join(Admission)
            .where(
                Admission.status == "active",
                func.lower(Patient.full_name) == payload.full_name.strip().lower(),
                Patient.age == payload.age,
            )
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"An active record already exists for {duplicate.patient_code}",
            )
        patient = Patient(
            patient_code=f"FW-{new_id()[:8].upper()}",
            full_name=payload.full_name.strip(),
            age=payload.age,
        )
        db.add(patient)
        db.flush()
        admission = Admission(patient_id=patient.id, bed_id=bed.id, created_by=user.id)
        db.add(admission)
        db.flush()
        record_audit(db, user, "admission.created", "admission", admission.id, bed.bed_code)
        db.commit()
        db.refresh(admission)
        return admission_view(db, admission)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Admission conflicts with an existing active record") from error
    except Exception:
        db.rollback()
        raise


@app.get("/api/v1/admissions/active")
def active_admissions(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    admissions = db.scalars(select(Admission).where(Admission.status == "active").order_by(Admission.admitted_at.desc())).all()
    return [admission_view(db, admission) for admission in admissions]


@app.get("/api/v1/nurse-tasks")
def nurse_tasks(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    require_role(user, "admin", "nurse")
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    today = facility_today(tz_name)
    return [patient_summary(db, patient, today, tz_name) for patient in active_patients(db)]


@app.get("/api/v1/patients/{patient_id}/temperatures")
def temperatures(patient_id: str, user: User = Depends(signed_in), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Patient was not found")
    rows = db.scalars(
        select(TemperatureReading).where(TemperatureReading.patient_id == patient_id).order_by(TemperatureReading.measured_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "value_c": row.value_c,
            "unit_entered": row.unit_entered,
            "measured_at": row.measured_at.isoformat(),
            "local_date": row.local_date.isoformat(),
            "status": row.status,
            "correction_reason": row.correction_reason,
            "recorded_at": row.recorded_at.isoformat(),
            "note": row.note,
        }
        for row in rows
    ]


@app.post("/api/v1/patients/{patient_id}/temperatures")
def add_temperature(
    patient_id: str,
    payload: TemperatureInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "nurse")
    admission = active_admission(db, patient_id)
    if not admission:
        raise HTTPException(status_code=409, detail="Temperature entry requires an active admission")
    measured = payload.measured_at
    if measured.tzinfo is None:
        measured = measured.replace(tzinfo=UTC)
    if measured > datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Measurement time cannot be in the future")
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    local_date = local_date_for(measured, tz_name)
    existing = db.scalar(
        select(TemperatureReading.id).where(
            TemperatureReading.admission_id == admission.id,
            TemperatureReading.local_date == local_date,
            TemperatureReading.status == "accepted",
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="A routine temperature is already recorded for this local date")
    value_c = payload.value if payload.unit == "C" else (payload.value - 32) * 5 / 9
    reading = TemperatureReading(
        patient_id=patient_id,
        admission_id=admission.id,
        value_c=round(value_c, 2),
        unit_entered=payload.unit,
        measured_at=measured.astimezone(UTC),
        local_date=local_date,
        recorded_by=user.id,
        note=payload.note.strip(),
    )
    db.add(reading)
    db.flush()
    record_audit(db, user, "temperature.recorded", "temperature", reading.id)
    db.commit()
    return {
        "id": reading.id,
        "value_c": reading.value_c,
        "unit_entered": reading.unit_entered,
        "measured_at": reading.measured_at.isoformat(),
        "local_date": local_date.isoformat(),
        "status": "recorded",
    }


@app.post("/api/v1/patients/{patient_id}/temperatures/{reading_id}/correction")
def correct_temperature(
    patient_id: str,
    reading_id: str,
    payload: TemperatureCorrectionInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "nurse")
    admission = active_admission(db, patient_id)
    original = db.get(TemperatureReading, reading_id)
    if (
        not admission
        or not original
        or original.patient_id != patient_id
        or original.admission_id != admission.id
        or original.status != "accepted"
    ):
        raise HTTPException(status_code=404, detail="Active temperature reading was not found")
    original.status = "superseded"
    value_c = payload.value if payload.unit == "C" else (payload.value - 32) * 5 / 9
    correction = TemperatureReading(
        patient_id=patient_id,
        admission_id=admission.id,
        value_c=round(value_c, 2),
        unit_entered=payload.unit,
        measured_at=original.measured_at,
        local_date=original.local_date,
        recorded_by=user.id,
        correction_of_id=original.id,
        correction_reason=payload.reason.strip(),
        note=original.note,
    )
    db.add(correction)
    db.flush()
    record_audit(db, user, "temperature.corrected", "temperature", correction.id, payload.reason.strip())
    db.commit()
    return {
        "id": correction.id,
        "value_c": correction.value_c,
        "unit_entered": correction.unit_entered,
        "local_date": correction.local_date.isoformat(),
        "status": correction.status,
        "correction_of_id": original.id,
    }


@app.get("/api/v1/doctor-queue")
def doctor_queue(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    require_role(user, "admin", "doctor")
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    today = facility_today(tz_name)
    return [patient_summary(db, patient, today, tz_name) for patient in active_patients(db)]


@app.get("/api/v1/patients/{patient_id}/visits")
def patient_visits(patient_id: str, user: User = Depends(signed_in), db: Session = Depends(get_db)):
    rows = db.scalars(select(DoctorVisit).where(DoctorVisit.patient_id == patient_id).order_by(DoctorVisit.visited_at.desc())).all()
    return [
        {
            "id": row.id,
            "visited_at": row.visited_at.isoformat(),
            "local_date": row.local_date.isoformat(),
            "notes": row.notes,
            "urgent_reason": row.urgent_reason,
        }
        for row in rows
    ]


@app.post("/api/v1/patients/{patient_id}/visits")
def add_visit(
    patient_id: str,
    payload: VisitInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "doctor")
    admission = active_admission(db, patient_id)
    if not admission:
        raise HTTPException(status_code=409, detail="Doctor visit requires an active admission")
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    now = datetime.now(UTC)
    visited_at = payload.visited_at or now
    if visited_at.tzinfo is None:
        visited_at = visited_at.replace(tzinfo=UTC)
    if visited_at > now:
        raise HTTPException(status_code=422, detail="Visit time cannot be in the future")
    local_date = local_date_for(visited_at, tz_name)
    has_temperature = db.scalar(
        select(TemperatureReading.id).where(
            TemperatureReading.admission_id == admission.id,
            TemperatureReading.local_date == local_date,
            TemperatureReading.status == "accepted",
        )
    )
    if not has_temperature and not payload.urgent_reason.strip():
        raise HTTPException(status_code=422, detail="Add an urgent-care reason to record a visit before temperature")
    if db.scalar(
        select(DoctorVisit.id).where(
            DoctorVisit.admission_id == admission.id,
            DoctorVisit.local_date == local_date,
        )
    ):
        raise HTTPException(status_code=409, detail="A routine doctor visit is already recorded for this local date")
    visit = DoctorVisit(
        patient_id=patient_id,
        admission_id=admission.id,
        doctor_id=user.id,
        visited_at=visited_at.astimezone(UTC),
        local_date=local_date,
        notes=payload.notes.strip(),
        urgent_reason=payload.urgent_reason.strip(),
    )
    db.add(visit)
    db.flush()
    record_audit(db, user, "doctor_visit.recorded", "doctor_visit", visit.id)
    db.commit()
    return {"id": visit.id, "local_date": local_date.isoformat(), "status": "recorded"}


@app.post("/api/v1/patients/{patient_id}/outcome")
def record_outcome(
    patient_id: str,
    payload: OutcomeInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "doctor")
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        admission = active_admission(db, patient_id)
        if not admission:
            raise HTTPException(status_code=409, detail="An active admission is required to record an outcome")
        now = datetime.now(UTC)
        admission.status = "closed"
        admission.discharged_at = now
        admission.closed_by = user.id
        outcome = PatientOutcome(
            admission_id=admission.id,
            patient_id=patient_id,
            outcome_type="deceased",
            outcome_at=now,
            recorded_by=user.id,
            notes=payload.notes.strip(),
        )
        db.add(outcome)
        record_audit(db, user, "patient.outcome.recorded", "admission", admission.id)
        db.commit()
        return {"admission_id": admission.id, "outcome": "deceased", "bed_released": True}
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An outcome has already been recorded") from error
    except Exception:
        db.rollback()
        raise


@app.get("/api/v1/patients/{patient_id}/eligibility")
def patient_eligibility(patient_id: str, user: User = Depends(signed_in), db: Session = Depends(get_db)):
    if not db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Patient was not found")
    return eligibility_for_patient(db, patient_id)


@app.get("/api/v1/discharge-eligibility")
def discharge_eligibility(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    today = facility_today(tz_name)
    eligible = []
    for patient in active_patients(db):
        result = eligibility_for_patient(db, patient.id)
        if result["eligible"]:
            eligible.append({**patient_summary(db, patient, today, tz_name), "evidence": result})
    return eligible


@app.get("/api/v1/discharge-review")
def discharge_review_queue(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    require_role(user, "admin", "doctor")
    result = []
    for item in discharge_eligibility(user, db):
        review = db.scalar(
            select(DischargeReview).where(DischargeReview.admission_id == item["admission_id"]).order_by(DischargeReview.reviewed_at.desc())
        )
        result.append(
            {
                **item,
                "doctor_reviewed": review is not None,
                "review_notes": review.notes if review else "",
            }
        )
    return result


@app.post("/api/v1/admissions/{admission_id}/discharge-review")
def add_discharge_review(
    admission_id: str,
    payload: ReviewInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "doctor")
    admission = db.get(Admission, admission_id)
    if not admission or admission.status != "active":
        raise HTTPException(status_code=404, detail="Active admission was not found")
    evidence = eligibility_for_patient(db, admission.patient_id)
    if not evidence["eligible"]:
        raise HTTPException(status_code=409, detail=evidence["reason"])
    review = DischargeReview(admission_id=admission.id, doctor_id=user.id, notes=payload.notes.strip())
    db.add(review)
    db.flush()
    record_audit(db, user, "discharge.reviewed", "admission", admission.id)
    db.commit()
    return {"id": review.id, "doctor_reviewed": True}


@app.post("/api/v1/admissions/{admission_id}/discharge")
def discharge(
    admission_id: str,
    payload: DischargeInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "admin")
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        admission = db.get(Admission, admission_id)
        if not admission or admission.status != "active":
            raise HTTPException(status_code=409, detail="Admission is already closed or missing")
        evidence = eligibility_for_patient(db, admission.patient_id)
        if not evidence["eligible"]:
            raise HTTPException(status_code=409, detail=evidence["reason"])
        review_required = setting(db, "discharge_requires_doctor_review", "true").lower() == "true"
        review = db.scalar(
            select(DischargeReview).where(DischargeReview.admission_id == admission.id).order_by(DischargeReview.reviewed_at.desc())
        )
        if review_required and not review:
            raise HTTPException(status_code=409, detail="A doctor discharge review is required first")
        now = datetime.now(UTC)
        admission.status = "closed"
        admission.discharged_at = now
        admission.closed_by = user.id
        db.add(
            Discharge(
                admission_id=admission.id,
                patient_id=admission.patient_id,
                discharged_at=now,
                finalized_by=user.id,
                notes=payload.notes.strip(),
            )
        )
        db.add(
            PatientOutcome(
                admission_id=admission.id,
                patient_id=admission.patient_id,
                outcome_type="discharged_alive",
                outcome_at=now,
                recorded_by=user.id,
                notes=payload.notes.strip(),
            )
        )
        record_audit(db, user, "admission.discharged", "admission", admission.id)
        db.commit()
        return {"admission_id": admission.id, "status": "discharged", "bed_released": True}
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="This admission has already been discharged") from error
    except Exception:
        db.rollback()
        raise


@app.get("/api/v1/dashboard/summary")
def dashboard(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    require_role(user, "admin", "nurse", "doctor")
    total = int(setting(db, "facility_capacity", "74"))
    active = active_patients(db)
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    today = facility_today(tz_name)
    summaries = [patient_summary(db, patient, today, tz_name) for patient in active]
    outcome_rows = db.scalars(select(PatientOutcome)).all()
    outcomes = len(outcome_rows)
    deaths = sum(1 for row in outcome_rows if row.outcome_type == "deceased")
    alive = sum(1 for row in outcome_rows if row.outcome_type == "discharged_alive")
    outcome_dates = sorted(local_date_for(row.outcome_at, tz_name).isoformat() for row in outcome_rows)
    return {
        "capacity": total,
        "occupied": len(active),
        "available": max(0, total - len(active)),
        "temperature_recorded": sum(row["temperature_status"] == "recorded" for row in summaries),
        "temperature_pending": sum(row["temperature_status"] != "recorded" for row in summaries),
        "visits_recorded": sum(row["doctor_visit_status"] == "recorded" for row in summaries),
        "visits_pending": sum(row["doctor_visit_status"] == "pending" for row in summaries),
        "eligible_for_review": sum(row["eligible"] for row in summaries),
        "fever_threshold_c": float(setting(db, "fever_threshold_c", "38.0")),
        "facility_timezone": tz_name,
        "outcomes": {
            "label": "Synthetic demo data",
            "deaths": deaths,
            "alive": alive,
            "denominator": outcomes,
            "period_start": outcome_dates[0] if outcome_dates else None,
            "period_end": outcome_dates[-1] if outcome_dates else None,
            "mortality_rate": round(deaths / outcomes * 100, 1) if outcomes else None,
            "survival_rate": round(alive / outcomes * 100, 1) if outcomes else None,
            "mortality_benchmark": 15,
            "survival_benchmark": 85,
        },
    }


@app.get("/api/v1/dashboard/daily-operations")
def daily_operations(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    return active_admissions(user, db)


@app.get("/api/v1/dashboard/export.csv")
def export_csv(request: Request, user: User = Depends(signed_in), db: Session = Depends(get_db)):
    require_role(user, "admin")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Patient code", "Patient", "Bed", "Temperature today", "Doctor visit today", "Eligible"])
    tz_name = setting(db, "facility_timezone", "Asia/Kolkata")
    for patient in active_patients(db):
        row = patient_summary(db, patient, facility_today(tz_name), tz_name)
        writer.writerow(
            [
                row["patient_code"],
                row["full_name"],
                row["bed_code"],
                row["temperature_status"],
                row["doctor_visit_status"],
                "yes" if row["eligible"] else "no",
            ]
        )
    record_audit(db, user, "dashboard.exported", "dashboard", "active-patients")
    db.commit()
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="factwise-daily-operations.csv"'},
    )


@app.get("/api/v1/analytics/outcomes")
def outcomes(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    return dashboard(user, db)["outcomes"]


@app.post("/api/v1/intake-requests")
def create_intake(
    payload: IntakeInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "admin", "nurse")
    name = payload.full_name.strip() if payload.full_name else ""
    complete = bool(name) and payload.age is not None
    intake = IntakeRequest(
        full_name=name or None,
        age=payload.age,
        details=payload.details.strip(),
        status="ready" if complete else "needs_review",
        review_note="" if complete else "Missing patient name or age. Review before admission.",
        requested_by=user.id,
    )
    db.add(intake)
    db.flush()
    record_audit(db, user, "intake.created", "intake_request", intake.id, intake.status)
    db.commit()
    return {
        "id": intake.id,
        "status": intake.status,
        "review_note": intake.review_note,
        "created_at": intake.created_at.isoformat(),
    }


@app.get("/api/v1/intake-requests")
def list_intake(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    require_role(user, "admin", "nurse")
    rows = db.scalars(select(IntakeRequest).order_by(IntakeRequest.created_at.desc())).all()
    return [
        {
            "id": row.id,
            "full_name": row.full_name,
            "age": row.age,
            "details": row.details,
            "status": row.status,
            "review_note": row.review_note,
            "created_patient_id": row.created_patient_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.post("/api/v1/intake-requests/{request_id}/complete")
def complete_intake(
    request_id: str,
    payload: IntakeCompletionInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "admin")
    intake = db.get(IntakeRequest, request_id)
    if not intake or intake.status == "completed":
        raise HTTPException(status_code=404, detail="Open intake request was not found")
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        capacity = int(setting(db, "facility_capacity", "74"))
        occupied = db.scalar(select(func.count()).select_from(Admission).where(Admission.status == "active")) or 0
        bed = db.scalar(
            select(Bed)
            .where(
                Bed.is_active.is_(True),
                ~Bed.id.in_(select(Admission.bed_id).where(Admission.status == "active")),
            )
            .order_by(Bed.bed_code)
            .limit(1)
        )
        if occupied >= capacity or not bed:
            raise HTTPException(status_code=409, detail=f"Facility capacity reached ({capacity} beds)")
        duplicate = db.scalar(
            select(Patient)
            .join(Admission)
            .where(
                Admission.status == "active",
                func.lower(Patient.full_name) == payload.full_name.strip().lower(),
                Patient.age == payload.age,
            )
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"An active record already exists for {duplicate.patient_code}",
            )
        patient = Patient(
            patient_code=f"FW-{new_id()[:8].upper()}",
            full_name=payload.full_name.strip(),
            age=payload.age,
        )
        db.add(patient)
        db.flush()
        admission = Admission(patient_id=patient.id, bed_id=bed.id, created_by=user.id)
        db.add(admission)
        intake.full_name = patient.full_name
        intake.age = patient.age
        intake.details = payload.details.strip() or intake.details
        intake.status = "completed"
        intake.created_patient_id = patient.id
        intake.review_note = ""
        db.flush()
        record_audit(db, user, "intake.completed", "intake_request", intake.id)
        record_audit(db, user, "admission.created", "admission", admission.id, bed.bed_code)
        db.commit()
        return {
            "request_id": intake.id,
            "patient_id": patient.id,
            "admission_id": admission.id,
            "status": "completed",
        }
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Admission conflicts with an existing record") from error
    except Exception:
        db.rollback()
        raise


@app.post("/api/v1/ai/ask")
def ask_assistant(
    payload: AssistantInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    question = payload.question.strip()
    no_evidence = not question
    message = (
        "No question or supporting information was provided. This request is flagged for human review; no AI answer was generated."
        if no_evidence
        else "The document knowledge base is not configured. This request is flagged for human review; do not rely on an AI answer."
    )
    item = AssistantRequest(
        question=question,
        status="needs_review",
        answer=message,
        review_note="Insufficient approved information for an answer.",
        requested_by=user.id,
    )
    db.add(item)
    db.flush()
    record_audit(db, user, "assistant.requested", "assistant_request", item.id, "needs_review")
    db.commit()
    return {
        "id": item.id,
        "status": item.status,
        "answer": item.answer,
        "human_review_required": True,
        "ai_used": False,
    }


@app.get("/api/v1/ai/requests")
def assistant_requests(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    require_role(user, "admin", "doctor")
    rows = db.scalars(select(AssistantRequest).order_by(AssistantRequest.created_at.desc())).all()
    return [
        {
            "id": row.id,
            "question": row.question,
            "status": row.status,
            "answer": row.answer,
            "review_note": row.review_note,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.post("/api/v1/ai/requests/{request_id}/review")
def review_assistant_request(
    request_id: str,
    payload: AssistantReviewInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "admin", "doctor")
    item = db.get(AssistantRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Assistant request was not found")
    item.status = "reviewed"
    item.review_note = payload.review_note.strip()
    item.reviewed_by = user.id
    item.reviewed_at = datetime.now(UTC)
    record_audit(db, user, "assistant.reviewed", "assistant_request", item.id)
    db.commit()
    return {"id": item.id, "status": item.status}


@app.get("/api/v1/settings")
def get_settings(user: User = Depends(signed_in), db: Session = Depends(get_db)):
    return {
        "fever_threshold_c": float(setting(db, "fever_threshold_c", "38.0")),
        "facility_timezone": setting(db, "facility_timezone", "Asia/Kolkata"),
        "discharge_requires_doctor_review": setting(db, "discharge_requires_doctor_review", "true") == "true",
        "facility_capacity": int(setting(db, "facility_capacity", "74")),
    }


@app.patch("/api/v1/settings")
def update_settings(
    payload: SettingsInput,
    request: Request,
    user: User = Depends(signed_in),
    db: Session = Depends(get_db),
):
    require_csrf(request)
    require_role(user, "admin")
    try:
        ZoneInfo(payload.facility_timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Unknown facility time zone") from error
    for key, value in (
        ("fever_threshold_c", str(payload.fever_threshold_c)),
        ("facility_timezone", payload.facility_timezone),
        (
            "discharge_requires_doctor_review",
            str(payload.discharge_requires_doctor_review).lower(),
        ),
    ):
        row = db.get(Setting, key)
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
    record_audit(db, user, "settings.updated", "settings", "facility")
    db.commit()
    return get_settings(user, db)


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        requested = frontend_dist / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")
