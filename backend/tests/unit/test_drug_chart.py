"""The inpatient drug chart's timing rules.

All times in these tests are hospital time (Asia/Kolkata, UTC+05:30) unless
they say otherwise, because that is the mistake the chart used to make.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.ipd import drug_chart as rules

pytestmark = pytest.mark.unit

IST = ZoneInfo("Asia/Kolkata")


def ist(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=IST).astimezone(timezone.utc)


# ------------------------------------------------------------- frequencies
def test_bd_defaults_to_the_morning_and_evening_rounds():
    assert rules.clock_times("BD") == [time(8), time(20)]


@pytest.mark.parametrize("written, code", [
    ("bd", "BD"), (" tid ", "TDS"), ("QDS", "QID"), ("prn", "SOS"), ("b.d.", "BD"),
])
def test_frequencies_are_read_the_way_charts_write_them(written, code):
    assert rules.normalise_frequency(written) == code


def test_explicit_times_override_the_defaults_sorted_and_deduplicated():
    assert rules.clock_times("BD", ["21:00", "09:00", "09:00", "nonsense"]) == [time(9), time(21)]


def test_as_needed_and_once_only_medicines_have_no_round_times():
    assert rules.clock_times("SOS") == []
    assert rules.clock_times("STAT") == []


def test_an_unknown_frequency_without_times_is_refused_not_ignored():
    with pytest.raises(rules.ScheduleError, match="Enter the times"):
        rules.clock_times("every other day")


# ----------------------------------------------------------- due moments
def test_round_times_are_hospital_time_not_utc():
    """The bug: 08:00 used to be scheduled at 08:00 UTC, 13:30 on the ward."""
    moments = rules.due_moments(
        [time(8)], start=ist(2026, 9, 13, 7), until=ist(2026, 9, 13, 12)
    )
    assert moments == [ist(2026, 9, 13, 8)]
    assert moments[0].hour == 2 and moments[0].minute == 30  # 02:30 UTC


def test_doses_are_laid_out_across_the_horizon():
    start = ist(2026, 9, 13, 7)
    moments = rules.due_moments(
        rules.clock_times("BD"), start=start, until=start + rules.SCHEDULE_HORIZON
    )
    assert moments == [ist(2026, 9, 13, 8), ist(2026, 9, 13, 20), ist(2026, 9, 14, 8)]


def test_a_dose_already_past_when_prescribed_is_not_scheduled():
    moments = rules.due_moments(
        rules.clock_times("BD"), start=ist(2026, 9, 13, 9), until=ist(2026, 9, 13, 23)
    )
    assert moments == [ist(2026, 9, 13, 20)]


def test_a_night_dose_crossing_midnight_lands_on_the_right_day():
    moments = rules.due_moments(
        rules.clock_times("Q6H"), start=ist(2026, 9, 13, 19), until=ist(2026, 9, 14, 7)
    )
    assert moments == [ist(2026, 9, 14, 0), ist(2026, 9, 14, 6)]


# ------------------------------------------------------- state and signing
@pytest.mark.parametrize("minutes_from_due, expected", [
    (-120, "upcoming"),
    (-59, "due"),
    (0, "due"),
    (59, "due"),
    (61, "overdue"),
])
def test_dose_state_follows_the_clock(minutes_from_due, expected):
    due = ist(2026, 9, 13, 8)
    now = due + timedelta(minutes=minutes_from_due)
    assert rules.dose_state(due_at=due, was_given=None, now=now) == expected


def test_signed_doses_keep_their_state_whatever_the_time():
    due = ist(2026, 9, 13, 8)
    later = due + timedelta(days=2)
    assert rules.dose_state(due_at=due, was_given=True, now=later) == "given"
    assert rules.dose_state(due_at=due, was_given=False, now=later) == "omitted"


def test_tomorrows_dose_cannot_be_signed_today():
    due = ist(2026, 9, 14, 8)
    assert not rules.can_sign(due_at=due, was_given=None, now=ist(2026, 9, 13, 20))
    assert rules.can_sign(due_at=due, was_given=None, now=ist(2026, 9, 14, 7, 30))


def test_a_signed_dose_cannot_be_signed_again():
    due = ist(2026, 9, 13, 8)
    assert not rules.can_sign(due_at=due, was_given=True, now=due)


# --------------------------------------------------------------- duplicates
def test_the_same_medicine_written_twice_is_a_serious_duplicate():
    """Regression: identical names were skipped before ingredients were compared."""
    from app.ai.pipeline.medication_rules import check_duplicates

    alerts = check_duplicates(["Pantoprazole", "pantoprazole "])
    assert [(alert.kind, alert.severity) for alert in alerts] == [("duplicate", "serious")]


def test_two_brands_of_one_drug_are_still_a_duplicate():
    from app.ai.pipeline.medication_rules import check_duplicates

    alerts = check_duplicates(["Pan", "Pantoprazole"])
    assert alerts and alerts[0].kind == "duplicate" and alerts[0].severity == "serious"


def test_different_medicines_are_not_duplicates():
    from app.ai.pipeline.medication_rules import check_duplicates

    assert check_duplicates(["Paracetamol", "Pantoprazole"]) == []
