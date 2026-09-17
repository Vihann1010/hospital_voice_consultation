"""Diet orders and the kitchen sheet."""
from datetime import datetime, time, timedelta, timezone

import pytest

from app.diet import rules

pytestmark = pytest.mark.unit

IST = timezone(timedelta(hours=5, minutes=30))
DAY = datetime(2026, 9, 14, tzinfo=IST)


def at(hour, minute=0, day=0):
    return DAY + timedelta(days=day, hours=hour, minutes=minute)


MEALS = [("Breakfast", at(8)), ("Lunch", at(13)), ("Dinner", at(20))]


def admission(**extra):
    base = {
        "id": "a1", "ip_number": "IP26-00001", "patient_name": "Asha", "age": 40, "gender": "female",
        "allergies": [], "admitted_at": at(-24), "discharged_at": None,
        "occupancies": [{"ward": "General", "bed": "G-1", "started_at": at(-24), "ended_at": None}],
        "leaves": [], "orders": [],
    }
    base.update(extra)
    return base


def order(name, start, end=None, instructions=None, nbm=False):
    return {"mode_name": name, "starts_at": start, "ends_at": end, "instructions": instructions,
            "is_nil_by_mouth": nbm}


def test_meal_times_parse_in_order():
    assert rules.parse_meal_times("Breakfast=08:00, Lunch=13:00,Dinner=20:00") == [
        ("Breakfast", time(8)), ("Lunch", time(13)), ("Dinner", time(20))]


@pytest.mark.parametrize("text", ["", "Breakfast", "Lunch=25:00", "Lunch=13:00,Breakfast=08:00",
                                  "Tea=16:00,tea=17:00"])
def test_malformed_meal_times_are_refused(text):
    with pytest.raises(ValueError):
        rules.parse_meal_times(text)


def test_start_time_limits():
    now = at(12)
    assert rules.check_start(at(11), now=now, admitted_at=at(-24)) is None
    assert "before the patient was admitted" in rules.check_start(at(-30), now=now, admitted_at=at(-24))
    assert "24 hours ago" in rules.check_start(at(-13), now=now, admitted_at=at(-48))
    assert "7 days ahead" in rules.check_start(at(12, day=8), now=now, admitted_at=at(-24))


def test_each_meal_uses_the_order_in_effect_at_that_meal():
    rows, counts = rules.build_sheet([admission(orders=[
        order("Liquid diet", at(-20), at(11)), order("Soft diet", at(11), instructions="No spice"),
    ])], MEALS)
    meals = rows[0]["meals"]
    assert meals["Breakfast"]["diet"] == "Liquid diet"
    assert meals["Lunch"]["diet"] == meals["Dinner"]["diet"] == "Soft diet"
    assert rows[0]["instructions"] == "No spice"
    assert counts["Breakfast"] == {"Liquid diet": 1} and counts["Dinner"] == {"Soft diet": 1}


def test_a_patient_with_no_order_is_listed_not_skipped():
    rows, counts = rules.build_sheet([admission()], MEALS)
    assert [cell["state"] for cell in rows[0]["meals"].values()] == ["no_order"] * 3
    assert counts["Lunch"] == {rules.NO_ORDER: 1}


def test_on_leave_at_mealtime_gets_no_tray():
    rows, counts = rules.build_sheet([admission(
        orders=[order("Normal diet", at(-20))],
        leaves=[{"started_at": at(10), "returned_at": at(18)}],
    )], MEALS)
    states = {label: cell["state"] for label, cell in rows[0]["meals"].items()}
    assert states == {"Breakfast": "diet", "Lunch": "on_leave", "Dinner": "diet"}
    assert counts["Lunch"] == {}


def test_admitted_after_breakfast_and_discharged_before_dinner():
    rows, _ = rules.build_sheet([admission(admitted_at=at(9), discharged_at=at(17),
                                           orders=[order("Normal diet", at(9))])], MEALS)
    states = [cell["state"] for cell in rows[0]["meals"].values()]
    assert states == ["absent", "diet", "absent"]


def test_nobody_present_at_any_meal_is_left_off():
    rows, _ = rules.build_sheet([admission(admitted_at=at(21))], MEALS)
    assert rows == []


def test_an_order_stopped_before_it_began_never_applies():
    rows, _ = rules.build_sheet([admission(orders=[
        order("Normal diet", at(-20), at(12)), order("Nil by mouth", at(12), at(12), nbm=True),
    ])], MEALS)
    assert rows[0]["meals"]["Lunch"]["state"] == "no_order"


def test_sheet_is_sorted_by_ward_and_bed():
    first = admission(id="a", patient_name="B", occupancies=[
        {"ward": "Private", "bed": "P-2", "started_at": at(-24), "ended_at": None}])
    second = admission(id="b", patient_name="A", occupancies=[
        {"ward": "General", "bed": "G-9", "started_at": at(-24), "ended_at": None}])
    rows, _ = rules.build_sheet([first, second], MEALS)
    assert [row["bed"] for row in rows] == ["G-9", "P-2"]
