"""Leave and room charges; which parts of a layout the system depends on."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.ipd.bed_days import Occupancy, compute_bed_days
from app.pads.defaults import default_layout
from app.services.pad_service import layout_protection_problems

pytestmark = pytest.mark.unit

IST = timezone(timedelta(hours=5, minutes=30))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=IST)


def bed(start, end=None, label="G-01"):
    return Occupancy(bed_id=label, bed_label=label, ward_name="General", rate_paise=100000,
                     started_at=start, ended_at=end)


def test_a_kept_bed_is_charged_through_the_leave():
    days = compute_bed_days([bed(at(1, 10))], admitted_at=at(1, 10), discharged_at=None, up_to=at(5, 9))
    assert [d.on.day for d in days] == [1, 2, 3, 4, 5]


def test_a_released_bed_is_not_charged_while_the_patient_is_away():
    # Left on the 2nd at 18:00 releasing the bed, came back on the 4th at 10:00 into another bed.
    occupancies = [bed(at(1, 10), at(2, 18)), bed(at(4, 10), label="G-05")]
    days = compute_bed_days(occupancies, admitted_at=at(1, 10), discharged_at=None, up_to=at(5, 9),
                            absences=[(at(2, 18), at(4, 10))])
    assert [(d.on.day, d.bed_label) for d in days] == [(1, "G-01"), (2, "G-01"), (5, "G-05")]


def test_without_the_absence_the_gap_would_have_been_billed_to_the_next_bed():
    occupancies = [bed(at(1, 10), at(2, 18)), bed(at(4, 10), label="G-05")]
    days = compute_bed_days(occupancies, admitted_at=at(1, 10), discharged_at=None, up_to=at(5, 9))
    assert [d.on.day for d in days] == [1, 2, 3, 4, 5]


def test_a_leave_still_open_stops_charges_until_today():
    days = compute_bed_days([bed(at(1, 10), at(2, 18))], admitted_at=at(1, 10), discharged_at=None,
                            up_to=at(6, 9), absences=[(at(2, 18), None)])
    assert [d.on.day for d in days] == [1, 2]


def test_the_discharge_summary_diagnosis_cannot_be_removed():
    layout = [s for s in default_layout("ipd_discharge_summary") if s["key"] != "final_diagnosis"]
    problems = layout_protection_problems("ipd_discharge_summary", layout)
    assert problems and "cannot be removed" in problems[0]


def test_the_pre_op_checks_must_stay_and_stay_required():
    layout = default_layout("ot_pre_op_checklist")
    checks = next(s for s in layout if s["key"] == "checks")
    checks["fields"] = [f for f in checks["fields"] if f["key"] != "consent_signed"]
    assert any("Consent form signed" in p or "consent_signed" in p
               for p in layout_protection_problems("ot_pre_op_checklist", layout))
    layout = default_layout("ot_pre_op_checklist")
    next(s for s in layout if s["key"] == "checks")["fields"][0]["required"] = False
    assert any("required" in p for p in layout_protection_problems("ot_pre_op_checklist", layout))


def test_reordering_and_renaming_is_fine():
    layout = list(reversed(default_layout("ipd_discharge_summary")))
    layout[0]["title"] = "A new title"
    assert layout_protection_problems("ipd_discharge_summary", layout) == []


def test_certificates_consents_and_radiology_layouts_are_locked():
    for key in ("cert_medical_leave", "consent_surgical", "radiology_report"):
        problems = layout_protection_problems(key, default_layout(key))
        assert problems and "fixed" in problems[0]
