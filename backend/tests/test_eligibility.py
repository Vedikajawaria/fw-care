from datetime import date, timedelta
from types import SimpleNamespace

from app.domain.eligibility import evaluate_eligibility


def reading(day: date, value: float):
    return SimpleNamespace(local_date=day, value_c=value)


def test_three_full_completed_days_qualify():
    today = date(2026, 11, 12)
    rows = [reading(today - timedelta(days=offset), 37.2) for offset in (1, 2, 3)]

    result = evaluate_eligibility(rows, 38.0, "Asia/Kolkata", today)

    assert result["eligible"] is True
    assert len(result["days"]) == 3


def test_missing_day_and_fever_today_do_not_qualify():
    today = date(2026, 11, 12)
    rows = [
        reading(today - timedelta(days=1), 37.2),
        reading(today - timedelta(days=3), 37.2),
    ]

    result = evaluate_eligibility(rows, 38.0, "Asia/Kolkata", today)
    assert result["eligible"] is False
    assert result["days"][1]["qualifies"] is False

    result = evaluate_eligibility([*rows, reading(today, 38.1)], 38.0, "Asia/Kolkata", today)
    assert result["eligible"] is False
    assert "Fever recorded today" in result["reason"]
