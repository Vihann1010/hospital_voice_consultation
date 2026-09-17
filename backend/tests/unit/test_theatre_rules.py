"""Operation theatre rules: times, durations, room clashes, and case states."""
from datetime import datetime, timedelta, timezone

import pytest

from app.theatre import rules

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 14, 4, 30, tzinfo=timezone.utc)  # 10:00 IST
NOW = T0 + timedelta(hours=4)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def full_case():
    times = {}
    for key, minutes in (
        ("wheel_in_at", 0), ("anaesthesia_start_at", 10), ("incision_at", 25),
        ("closure_at", 95), ("wheel_out_at", 110),
    ):
        times = rules.check_milestone(times, key, at(minutes), now=NOW)
    return times


# ----------------------------------------------------------------- states
@pytest.mark.parametrize("current, event, target", [
    ("scheduled", "wheel_in", "in_theatre"),
    ("in_theatre", "wheel_out", "completed"),
    ("scheduled", "cancel", "cancelled"),
])
def test_a_case_moves_forward(current, event, target):
    assert rules.next_status(current, event) == target


@pytest.mark.parametrize("current, event, message", [
    ("in_theatre", "cancel", "already in theatre cannot be cancelled"),
    ("scheduled", "wheel_out", "not been wheeled in"),
    ("completed", "wheel_in", "completed and cannot be changed"),
    ("cancelled", "wheel_in", "cancelled and cannot be changed"),
    ("in_theatre", "wheel_in", "already in theatre"),
])
def test_a_case_cannot_move_backwards_or_skip(current, event, message):
    with pytest.raises(rules.TheatreRuleError, match=message):
        rules.next_status(current, event)


# ------------------------------------------------------------- milestones
def test_a_whole_case_records_in_order_and_times_itself():
    assert rules.durations(full_case()) == {
        "theatre_minutes": 110, "surgery_minutes": 70, "anaesthesia_minutes": 100,
    }


def test_incision_needs_the_patient_in_theatre_first():
    with pytest.raises(rules.TheatreRuleError, match="Record wheeled in before incision"):
        rules.check_milestone({}, "incision_at", at(10), now=NOW)


def test_closure_needs_an_incision():
    times = rules.check_milestone({}, "wheel_in_at", at(0), now=NOW)
    with pytest.raises(rules.TheatreRuleError, match="Record incision before closure"):
        rules.check_milestone(times, "closure_at", at(60), now=NOW)


def test_closure_cannot_come_before_incision():
    times = rules.check_milestone({}, "wheel_in_at", at(0), now=NOW)
    times = rules.check_milestone(times, "incision_at", at(30), now=NOW)
    with pytest.raises(rules.TheatreRuleError, match="cannot be before incision"):
        rules.check_milestone(times, "closure_at", at(20), now=NOW)


def test_correcting_an_earlier_time_cannot_leapfrog_a_later_one():
    times = full_case()
    with pytest.raises(rules.TheatreRuleError, match="cannot be after closure"):
        rules.check_milestone(times, "incision_at", at(100), now=NOW)


def test_nothing_is_recorded_in_the_future_beyond_clock_drift():
    assert rules.check_milestone({}, "wheel_in_at", NOW + timedelta(minutes=3), now=NOW)
    with pytest.raises(rules.TheatreRuleError, match="in the future"):
        rules.check_milestone({}, "wheel_in_at", NOW + timedelta(minutes=30), now=NOW)


def test_a_patient_cannot_leave_theatre_with_an_open_incision():
    times = rules.check_milestone({}, "wheel_in_at", at(0), now=NOW)
    times = rules.check_milestone(times, "incision_at", at(20), now=NOW)
    with pytest.raises(rules.TheatreRuleError, match="without a closure"):
        rules.check_milestone(times, "wheel_out_at", at(90), now=NOW)


def test_a_case_abandoned_before_incision_can_still_wheel_out():
    times = rules.check_milestone({}, "wheel_in_at", at(0), now=NOW)
    times = rules.check_milestone(times, "wheel_out_at", at(15), now=NOW)
    assert rules.durations(times)["surgery_minutes"] is None


def test_unknown_milestones_are_refused():
    with pytest.raises(rules.TheatreRuleError, match="Unknown theatre time"):
        rules.check_milestone({}, "coffee_at", at(0), now=NOW)


# ------------------------------------------------------------------ rooms
def test_overlapping_cases_in_one_room_clash():
    new = rules.Booking("new", at(60), 90)
    others = [rules.Booking("a", at(0), 90), rules.Booking("b", at(200), 30)]
    assert [b.reference for b in rules.clashes(new, others)] == ["a"]


def test_back_to_back_cases_do_not_clash():
    new = rules.Booking("new", at(90), 60)
    assert rules.clashes(new, [rules.Booking("a", at(0), 90)]) == []


def test_a_case_does_not_clash_with_itself_when_rescheduled():
    booking = rules.Booking("same", at(0), 60)
    assert rules.clashes(booking, [booking]) == []
