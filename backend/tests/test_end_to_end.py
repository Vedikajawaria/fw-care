from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app


def sign_in(client: TestClient, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Demo123!"},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_admin_nurse_doctor_and_review_first_flows():
    with TestClient(app) as client:
        unauthenticated = client.get("/api/v1/auth/me")
        assert unauthenticated.status_code == 200
        assert unauthenticated.json()["user"] is None
        admin_headers = sign_in(client, "admin")
        occupancy = client.get("/api/v1/occupancy").json()
        assert occupancy == {"capacity": 74, "occupied": 72, "available": 2}

        empty_intake = client.post(
            "/api/v1/intake-requests",
            headers=admin_headers,
            json={"full_name": "", "age": None, "details": ""},
        )
        assert empty_intake.status_code == 200
        intake = empty_intake.json()
        assert intake["status"] == "needs_review"
        assert "Missing" in intake["review_note"]

        completed_intake = client.post(
            f"/api/v1/intake-requests/{intake['id']}/complete",
            headers=admin_headers,
            json={"full_name": "Review Queue Patient", "age": 31, "details": "Verified by staff"},
        )
        assert completed_intake.status_code == 200
        patient_id = completed_intake.json()["patient_id"]
        assert client.get("/api/v1/occupancy").json()["occupied"] == 73
        duplicate = client.post(
            "/api/v1/admissions",
            headers=admin_headers,
            json={"full_name": "Review Queue Patient", "age": 31},
        )
        assert duplicate.status_code == 409
        assert "active record" in duplicate.json()["detail"]
        second_admission = client.post(
            "/api/v1/admissions",
            headers=admin_headers,
            json={"full_name": "Capacity Patient", "age": 44},
        )
        assert second_admission.status_code == 200
        assert client.get("/api/v1/occupancy").json()["occupied"] == 74
        at_capacity = client.post(
            "/api/v1/admissions",
            headers=admin_headers,
            json={"full_name": "Blocked Capacity Patient", "age": 45},
        )
        assert at_capacity.status_code == 409
        assert "capacity reached" in at_capacity.json()["detail"]

        nurse_headers = sign_in(client, "nurse")
        forbidden_admission = client.post(
            "/api/v1/admissions",
            headers=nurse_headers,
            json={"full_name": "Unauthorized", "age": 20},
        )
        assert forbidden_admission.status_code == 403
        tasks = client.get("/api/v1/nurse-tasks").json()
        task = next(item for item in tasks if item["id"] == patient_id)
        assert task["temperature_status"] == "pending"
        overdue_task = next(item for item in tasks if item["patient_code"] == "FW-0002")
        assert overdue_task["temperature_status"] == "missed yesterday"
        for offset in (1, 2, 3):
            backdated = client.post(
                f"/api/v1/patients/{patient_id}/temperatures",
                headers=nurse_headers,
                json={
                    "value": 37.0,
                    "unit": "C",
                    "measured_at": (datetime.now(UTC).replace(hour=10, minute=0) - timedelta(days=offset)).isoformat(),
                },
            )
            assert backdated.status_code == 200
        assert client.get(f"/api/v1/patients/{patient_id}/eligibility").json()["eligible"] is False

        recorded = client.post(
            f"/api/v1/patients/{patient_id}/temperatures",
            headers=nurse_headers,
            json={"value": 98.6, "unit": "F", "measured_at": datetime.now(UTC).isoformat()},
        )
        assert recorded.status_code == 200
        assert abs(recorded.json()["value_c"] - 37.0) < 0.1
        correction = client.post(
            f"/api/v1/patients/{patient_id}/temperatures/{recorded.json()['id']}/correction",
            headers=nurse_headers,
            json={"value": 100.4, "unit": "F", "reason": "Corrected transcribed unit value"},
        )
        assert correction.status_code == 200
        assert abs(correction.json()["value_c"] - 38.0) < 0.1
        history = client.get(f"/api/v1/patients/{patient_id}/temperatures").json()
        assert {row["status"] for row in history} == {"accepted", "superseded"}
        assert any(row["correction_reason"] for row in history)
        duplicate = client.post(
            f"/api/v1/patients/{patient_id}/temperatures",
            headers=nurse_headers,
            json={"value": 37.1, "unit": "C", "measured_at": datetime.now(UTC).isoformat()},
        )
        assert duplicate.status_code == 409
        future_reading = client.post(
            f"/api/v1/patients/{task['id']}/temperatures",
            headers=nurse_headers,
            json={
                "value": 37.1,
                "unit": "C",
                "measured_at": (datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)).isoformat(),
            },
        )
        assert future_reading.status_code == 422

        blank_question = client.post(
            "/api/v1/ai/ask",
            headers=nurse_headers,
            json={"question": ""},
        )
        assert blank_question.status_code == 200
        assert blank_question.json()["status"] == "needs_review"
        assert blank_question.json()["human_review_required"] is True
        assert blank_question.json()["ai_used"] is False

        doctor_headers = sign_in(client, "doctor")
        assistant_review = client.post(
            f"/api/v1/ai/requests/{blank_question.json()['id']}/review",
            headers=doctor_headers,
            json={"review_note": "Reviewed without approved evidence"},
        )
        assert assistant_review.status_code == 200
        assert assistant_review.json()["status"] == "reviewed"
        queue = client.get("/api/v1/doctor-queue").json()
        task = next(item for item in queue if item["id"] == patient_id)
        assert task["temperature_status"] == "recorded"
        visit = client.post(
            f"/api/v1/patients/{patient_id}/visits",
            headers=doctor_headers,
            json={"notes": "Synthetic workflow test"},
        )
        assert visit.status_code == 200
        visit_task = next(item for item in client.get("/api/v1/doctor-queue").json() if item["id"] == patient_id)
        assert visit_task["doctor_visit_status"] == "recorded"
        pending_temperature_patient = next(item for item in client.get("/api/v1/doctor-queue").json() if item["patient_code"] == "FW-0003")
        blocked_visit = client.post(
            f"/api/v1/patients/{pending_temperature_patient['id']}/visits",
            headers=doctor_headers,
            json={"notes": "No temperature and no urgent reason"},
        )
        assert blocked_visit.status_code == 422
        urgent_visit = client.post(
            f"/api/v1/patients/{pending_temperature_patient['id']}/visits",
            headers=doctor_headers,
            json={"notes": "Urgent visit", "urgent_reason": "Urgent assessment required"},
        )
        assert urgent_visit.status_code == 200

        patient_list = client.get("/api/v1/patients").json()
        deceased_patient = next(item for item in patient_list if item["patient_code"] == "FW-0002")
        outcome = client.post(
            f"/api/v1/patients/{deceased_patient['id']}/outcome",
            headers=doctor_headers,
            json={"notes": "Synthetic demo outcome"},
        )
        assert outcome.status_code == 200
        assert outcome.json()["bed_released"] is True
        assert client.get("/api/v1/occupancy").json()["occupied"] == 73

        eligible = client.get("/api/v1/discharge-review").json()
        seeded_ready = next(item for item in eligible if item["patient_code"] == "FW-0001")
        review = client.post(
            f"/api/v1/admissions/{seeded_ready['admission_id']}/discharge-review",
            headers=doctor_headers,
            json={"notes": "Reviewed deterministic evidence"},
        )
        assert review.status_code == 200

        admin_headers = sign_in(client, "admin")
        discharged = client.post(
            f"/api/v1/admissions/{seeded_ready['admission_id']}/discharge",
            headers=admin_headers,
            json={"notes": "Synthetic test discharge"},
        )
        assert discharged.status_code == 200, discharged.text
        assert discharged.json()["bed_released"] is True
        assert client.get("/api/v1/occupancy").json()["occupied"] == 72

        summary = client.get("/api/v1/dashboard/summary").json()
        assert summary["outcomes"]["denominator"] == 4
        assert summary["outcomes"]["deaths"] == 2
        assert summary["fever_threshold_c"] == 38.0
        assert summary["outcomes"]["period_start"]
        assert summary["outcomes"]["period_end"]
        exported = client.get("/api/v1/dashboard/export.csv")
        assert exported.status_code == 200
        assert "Patient code,Patient,Bed" in exported.text
