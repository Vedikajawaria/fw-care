from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import TemperatureReading


def evaluate_eligibility(
    readings: Sequence[TemperatureReading],
    threshold_c: float,
    timezone_name: str,
    today: date,
) -> dict:
    by_day: dict[date, list[float]] = {}
    for reading in readings:
        by_day.setdefault(reading.local_date, []).append(reading.value_c)

    today_values = by_day.get(today, [])
    if any(value >= threshold_c for value in today_values):
        return {
            "eligible": False,
            "reason": "Fever recorded today; today is not a completed qualifying day.",
            "days": [],
        }

    examined = []
    for offset in range(1, 4):
        day = today - timedelta(days=offset)
        values = by_day.get(day, [])
        qualifies = bool(values) and all(value < threshold_c for value in values)
        examined.append(
            {
                "date": day.isoformat(),
                "readings_c": values,
                "qualifies": qualifies,
            }
        )
    eligible = all(entry["qualifies"] for entry in examined)
    reason = (
        "Meets configured 3-full-day fever-free rule."
        if eligible
        else "Three consecutive completed days below the configured threshold are not recorded."
    )
    return {"eligible": eligible, "reason": reason, "days": examined, "timezone": timezone_name}


def facility_today(timezone_name: str) -> date:
    return datetime.now(ZoneInfo(timezone_name)).date()
