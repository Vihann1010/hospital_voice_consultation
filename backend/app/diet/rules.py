"""Diet rules: when an order may start, and what the kitchen sends to each bed.

Pure functions over plain values, so the kitchen sheet is tested directly.

**A meal is served against the order in effect at that meal's time.** A diet
changed from liquid to soft at eleven is liquid at breakfast and soft at lunch,
and the sheet says so per meal rather than showing only the latest order.

**Silence is never a diet.** A patient in a bed with no diet order is listed
as having none, loudly, rather than left off the sheet or assumed to be on a
normal diet. A patient away on leave at mealtime is shown as on leave, so no
tray goes to an empty bed.
"""
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

BACKDATE_LIMIT = timedelta(hours=24)
FUTURE_LIMIT = timedelta(days=7)
MAX_INSTRUCTIONS = 500

NO_ORDER = "No diet order"


def parse_meal_times(text: str) -> List[Tuple[str, time]]:
    """"Breakfast=08:00,Lunch=13:00,Dinner=20:00" -> [(label, time), ...].

    Raises ValueError on anything malformed: a kitchen sheet built from a
    half-read setting would quietly drop a meal.
    """
    meals: List[Tuple[str, time]] = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        label, sep, clock = part.partition("=")
        label = label.strip()
        if not sep or not label or len(label) > 20:
            raise ValueError(f"Meal time {part!r} should look like Lunch=13:00")
        try:
            hours, minutes = clock.strip().split(":")
            at = time(int(hours), int(minutes))
        except ValueError as exc:
            raise ValueError(f"Meal time {part!r} has an invalid time") from exc
        meals.append((label, at))
    if not meals:
        raise ValueError("At least one meal time is needed")
    for (_, earlier), (label, later) in zip(meals, meals[1:]):
        if later <= earlier:
            raise ValueError(f"{label} must come after the meal before it")
    if len({label.lower() for label, _ in meals}) != len(meals):
        raise ValueError("Two meals have the same name")
    return meals


def check_start(start: datetime, *, now: datetime, admitted_at: datetime) -> Optional[str]:
    """Why a diet order may not start then, or None."""
    if start < admitted_at:
        return "A diet order cannot start before the patient was admitted."
    if start < now - BACKDATE_LIMIT:
        return "A diet order cannot start more than 24 hours ago."
    if start > now + FUTURE_LIMIT:
        return "A diet order cannot start more than 7 days ahead."
    return None


def _within(moment: datetime, start: datetime, end: Optional[datetime]) -> bool:
    return start <= moment and (end is None or moment < end)


def order_at(orders: Sequence[Dict[str, Any]], moment: datetime) -> Optional[Dict[str, Any]]:
    """The order in effect at a moment. An order stopped before it began is none."""
    for order in orders:
        if order.get("ends_at") is not None and order["ends_at"] <= order["starts_at"]:
            continue
        if _within(moment, order["starts_at"], order.get("ends_at")):
            return order
    return None


def build_sheet(
    admissions: Sequence[Dict[str, Any]], meals: Sequence[Tuple[str, datetime]]
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, int]]]:
    """One row per patient present at any meal of the day, and trays per diet per meal.

    Each admission is a dict with ip_number, patient_name, age, gender,
    allergies, admitted_at, discharged_at, and lists of occupancies (ward, bed,
    started_at, ended_at), leaves (started_at, returned_at) and orders
    (mode_name, is_nil_by_mouth, instructions, starts_at, ends_at).
    """
    rows: List[Dict[str, Any]] = []
    counts: Dict[str, Dict[str, int]] = {label: {} for label, _ in meals}

    for entry in admissions:
        cells: Dict[str, Dict[str, Any]] = {}
        present = False
        place = None
        notes: List[str] = []
        for label, moment in meals:
            blank = {"state": "absent", "diet": None, "nil_by_mouth": False, "instructions": None}
            if not _within(moment, entry["admitted_at"], entry.get("discharged_at")):
                cells[label] = blank
                continue
            present = True
            here = next((o for o in entry.get("occupancies", [])
                         if _within(moment, o["started_at"], o.get("ended_at"))), None)
            if here is not None:
                place = here
            if any(_within(moment, leave["started_at"], leave.get("returned_at"))
                   for leave in entry.get("leaves", [])):
                cells[label] = {**blank, "state": "on_leave"}
                continue
            order = order_at(entry.get("orders", []), moment)
            if order is None:
                cells[label] = {**blank, "state": "no_order"}
                counts[label][NO_ORDER] = counts[label].get(NO_ORDER, 0) + 1
                continue
            cells[label] = {
                "state": "diet",
                "diet": order["mode_name"],
                "nil_by_mouth": bool(order.get("is_nil_by_mouth")),
                "instructions": order.get("instructions"),
            }
            counts[label][order["mode_name"]] = counts[label].get(order["mode_name"], 0) + 1
            if order.get("instructions") and order["instructions"] not in notes:
                notes.append(order["instructions"])
        if not present:
            continue
        if place is None and entry.get("occupancies"):
            place = max(entry["occupancies"], key=lambda o: o["started_at"])
        rows.append({
            "admission_id": entry.get("id"),
            "ip_number": entry["ip_number"],
            "patient_name": entry["patient_name"],
            "age": entry.get("age"),
            "gender": entry.get("gender"),
            "allergies": list(entry.get("allergies") or []),
            "ward": place["ward"] if place else "",
            "bed": place["bed"] if place else "",
            "meals": cells,
            "instructions": "; ".join(notes) or None,
        })
    rows.sort(key=lambda row: (row["ward"] or "~", row["bed"] or "~", row["patient_name"]))
    return rows, counts
