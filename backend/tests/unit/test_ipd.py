"""Bed-day accrual and NEWS2.

Two calculations where a silent error is expensive. Bed-days are money that
nobody audits until the year end; NEWS2 is a patient who is deteriorating
while the ward believes they are fine.
"""
from datetime import date, datetime

import pytest

from app.ipd.bed_days import (
    BedDayError, Occupancy, compute_bed_days, occupancy_at, total_bed_charge_paise,
)
from app.ipd.early_warning import Vitals, VitalsError, score_news2, trend

pytestmark = pytest.mark.unit

GENERAL_RATE = 150000
ICU_RATE = 600000


def general(start, end=None):
    return Occupancy("b1", "G-12", "General Ward", GENERAL_RATE, start, end)


def icu(start, end=None):
    return Occupancy("b2", "ICU-3", "ICU", ICU_RATE, start, end)


# --------------------------------------------------------------- bed days
def test_overnight_stay_is_one_day_not_two():
    """Admitted 23:00, home at 09:00 — ten hours is one bed-day."""
    admitted = datetime(2026, 8, 10, 23, 0)
    discharged = datetime(2026, 8, 11, 9, 0)
    assert len(compute_bed_days([general(admitted, discharged)],
                                admitted_at=admitted, discharged_at=discharged)) == 1


def test_staying_past_the_cutoff_charges_the_discharge_day():
    admitted = datetime(2026, 8, 10, 23, 0)
    discharged = datetime(2026, 8, 11, 16, 0)
    assert len(compute_bed_days([general(admitted, discharged)],
                                admitted_at=admitted, discharged_at=discharged)) == 2


def test_same_day_admission_and_discharge_is_one_day():
    """A bed was taken out of service, however briefly."""
    admitted = datetime(2026, 8, 10, 9, 0)
    discharged = datetime(2026, 8, 10, 15, 0)
    assert len(compute_bed_days([general(admitted, discharged)],
                                admitted_at=admitted, discharged_at=discharged)) == 1


def test_a_transfer_never_charges_one_day_to_two_beds():
    """The bug that quietly doubles a ward's revenue and its complaints."""
    admitted = datetime(2026, 8, 10, 10, 0)
    moved = datetime(2026, 8, 12, 14, 0)
    discharged = datetime(2026, 8, 15, 16, 0)
    charges = compute_bed_days(
        [general(admitted, moved), icu(moved, discharged)],
        admitted_at=admitted, discharged_at=discharged,
    )
    days = [charge.on for charge in charges]
    assert len(days) == len(set(days))
    assert len(charges) == 6


@pytest.mark.parametrize(
    "move_hour,expected_ward",
    [(6, "ICU"), (14, "General Ward")],
)
def test_the_census_hour_decides_whose_day_it_is(move_hour, expected_ward):
    """Moved before the census hour, the day belongs to the new bed."""
    admitted = datetime(2026, 8, 10, 10, 0)
    moved = datetime(2026, 8, 12, move_hour, 0)
    discharged = datetime(2026, 8, 13, 16, 0)
    charges = compute_bed_days(
        [general(admitted, moved), icu(moved, discharged)],
        admitted_at=admitted, discharged_at=discharged, charging_hour=8,
    )
    on_move_day = next(c for c in charges if c.on == date(2026, 8, 12))
    assert on_move_day.ward_name == expected_ward


def test_rate_follows_the_bed_the_patient_was_actually_in():
    admitted = datetime(2026, 8, 10, 10, 0)
    moved = datetime(2026, 8, 12, 6, 0)
    discharged = datetime(2026, 8, 13, 16, 0)
    charges = compute_bed_days(
        [general(admitted, moved), icu(moved, discharged)],
        admitted_at=admitted, discharged_at=discharged,
    )
    # 10th, 11th at ward rate; 12th, 13th at ICU rate.
    assert total_bed_charge_paise(charges) == GENERAL_RATE * 2 + ICU_RATE * 2


def test_an_ongoing_stay_can_be_billed_to_a_point_in_time():
    admitted = datetime(2026, 8, 10, 10, 0)
    charges = compute_bed_days([general(admitted)], admitted_at=admitted,
                               discharged_at=None, up_to=datetime(2026, 8, 13, 9, 0))
    assert len(charges) == 4


def test_discharge_before_admission_is_rejected():
    admitted = datetime(2026, 8, 10, 10, 0)
    with pytest.raises(BedDayError):
        compute_bed_days([general(admitted)], admitted_at=admitted,
                         discharged_at=datetime(2026, 8, 9, 10, 0))


def test_a_stay_with_no_bed_is_rejected():
    with pytest.raises(BedDayError):
        compute_bed_days([], admitted_at=datetime(2026, 8, 10, 10, 0),
                         discharged_at=None)


def test_the_transfer_moment_belongs_to_the_new_bed():
    moved = datetime(2026, 8, 12, 14, 0)
    held = occupancy_at(
        [general(datetime(2026, 8, 10, 10, 0), moved), icu(moved)], moved
    )
    assert held is not None and held.ward_name == "ICU"


# ------------------------------------------------------------------ NEWS2
def test_a_well_patient_scores_zero():
    result = score_news2(Vitals(respiratory_rate=16, spo2_percent=98, systolic_bp=120,
                                pulse=70, temperature_c=36.8, consciousness="A"))
    assert result.total == 0
    assert result.risk == "none"


def test_rcp_worked_example_septic_patient():
    """RR 24(2) SpO2 93(2) oxygen(2) SBP 95(2) HR 115(2) T 38.5(1) alert(0)."""
    result = score_news2(Vitals(respiratory_rate=24, spo2_percent=93, on_oxygen=True,
                                systolic_bp=95, pulse=115, temperature_c=38.5,
                                consciousness="A"))
    assert result.total == 11
    assert result.risk == "critical"


def test_one_severely_abnormal_parameter_escalates_alone():
    """A total of 3 from a single parameter is not the same as 3 spread out."""
    result = score_news2(Vitals(respiratory_rate=16, spo2_percent=98, systolic_bp=120,
                                pulse=38, temperature_c=36.8, consciousness="A"))
    assert result.total == 3
    assert result.red_score
    assert result.risk == "medium"


def test_new_confusion_scores_three():
    """The parameter clinicians miss most often."""
    result = score_news2(Vitals(respiratory_rate=16, spo2_percent=98, systolic_bp=120,
                                pulse=70, temperature_c=36.8, consciousness="C"))
    assert result.total == 3
    assert result.red_score


def test_scale_2_stops_copd_patients_triggering_false_alarms():
    """On scale 1 a COPD patient at their own baseline looks like they are
    deteriorating, which teaches staff to ignore the score."""
    observations = dict(respiratory_rate=18, spo2_percent=89, systolic_bp=130,
                        pulse=80, temperature_c=36.5, consciousness="A")
    assert score_news2(Vitals(**observations)).total == 3
    assert score_news2(Vitals(**observations, spo2_scale_2=True)).total == 0


def test_over_oxygenation_on_scale_2_is_itself_scored():
    """For this group, too much oxygen is the danger."""
    result = score_news2(Vitals(respiratory_rate=18, spo2_percent=97, on_oxygen=True,
                                systolic_bp=130, pulse=80, temperature_c=36.5,
                                consciousness="A", spo2_scale_2=True))
    assert result.total >= 5


def test_missing_observations_are_reported_not_assumed_normal():
    result = score_news2(Vitals(respiratory_rate=18, pulse=80))
    assert not result.is_complete
    assert "temperature" in result.missing


def test_supplemental_oxygen_scores_on_its_own():
    on_air = score_news2(Vitals(respiratory_rate=16, spo2_percent=98, systolic_bp=120,
                                pulse=70, temperature_c=36.8, consciousness="A"))
    on_oxygen = score_news2(Vitals(respiratory_rate=16, spo2_percent=98, on_oxygen=True,
                                   systolic_bp=120, pulse=70, temperature_c=36.8,
                                   consciousness="A"))
    assert on_oxygen.total - on_air.total == 2


@pytest.mark.parametrize(
    "field,value",
    [("respiratory_rate", 250), ("spo2_percent", 20), ("systolic_bp", 500),
     ("pulse", 400), ("temperature_c", 60.0)],
)
def test_impossible_observations_are_rejected(field, value):
    """A mistyped observation must not silently produce a plausible score."""
    with pytest.raises(VitalsError):
        score_news2(Vitals(**{field: value}))


def test_trend_detects_a_patient_going_downhill():
    scores = [
        score_news2(Vitals(respiratory_rate=rate, spo2_percent=97, systolic_bp=120,
                           pulse=80, temperature_c=37.0, consciousness="A"))
        for rate in (16, 21, 25)
    ]
    assert trend(scores)["direction"] == "deteriorating"
