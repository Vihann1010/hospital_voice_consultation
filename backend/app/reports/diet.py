"""The kitchen's day sheet, as a report: the same rows the ward's Diet screen
shows, so it can be exported and filed with the rest.

A clinical report with no money in it, open to anyone who can read a patient.
"""
from datetime import date
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.diet import rules
from app.reports.definitions import Column, ReportSpec, register

try:
    _MEALS = rules.parse_meal_times(settings.DIET_MEAL_TIMES)
except ValueError:
    _MEALS = rules.parse_meal_times("Breakfast=08:00,Lunch=13:00,Dinner=20:00")

KITCHEN = ReportSpec(
    key="kitchen-diet",
    title="Kitchen diet sheet",
    description="Every inpatient's diet at each meal of the day, with instructions and allergies.",
    single_day=True,
    permission="patient:read",
    columns=[
        Column("ward", "Ward"),
        Column("bed", "Bed"),
        Column("ip_number", "IP number", default_visible=False),
        Column("patient_name", "Patient"),
        Column("age_sex", "Age / sex"),
        *[Column(f"meal_{index}", label) for index, (label, _) in enumerate(_MEALS)],
        Column("instructions", "Instructions"),
        Column("allergies", "Allergies"),
    ],
)

_STATE_TEXT = {"on_leave": "On leave", "no_order": "NO DIET ORDER", "absent": ""}


async def _kitchen(session: AsyncSession, *, date_from: date, **_: Any) -> List[Dict[str, Any]]:
    from app.services.diet_service import DietService

    sheet = await DietService(session).kitchen(date_from)
    rows = []
    for row in sheet["rows"]:
        out = {
            "ward": row["ward"], "bed": row["bed"], "ip_number": row["ip_number"],
            "patient_name": row["patient_name"],
            "age_sex": f"{row['age']} / {(row['gender'] or '')[:1].upper()}",
            "instructions": row["instructions"] or "",
            "allergies": ", ".join(row["allergies"]),
        }
        for index, meal in enumerate(sheet["meals"]):
            cell = row["meals"].get(meal["label"], {})
            out[f"meal_{index}"] = cell.get("diet") if cell.get("state") == "diet" \
                else _STATE_TEXT.get(cell.get("state"), "")
        rows.append(out)
    return rows


register(KITCHEN, _kitchen)
