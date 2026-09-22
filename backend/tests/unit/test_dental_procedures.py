"""Dental cases: which teeth, and the notes a dental case is written up in."""
import pytest

from app.models.enums import Department
from app.pads.defaults import PROTECTED_SECTIONS, REGISTRY
from app.services.theatre_service import PRE_PROCEDURE_CHECKLISTS, notes_for
from app.theatre import rules

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw,stored",
    [("36", "36"), ("36, 37", "36, 37"), ("11 21", "11, 21"), ("36,36", "36"),
     ("85", "85"), ("full mouth", "Full mouth"), ("Upper arch", "Upper arch")],
)
def test_teeth_are_read_in_fdi(raw, stored):
    assert rules.parse_teeth(raw) == stored


@pytest.mark.parametrize("raw", ["", None, "19", "39", "56", "90", "3", "left molar", "36, 99"])
def test_a_tooth_that_does_not_exist_is_refused(raw):
    with pytest.raises(rules.TheatreRuleError):
        rules.parse_teeth(raw)


def test_a_dental_case_gets_dental_notes_only():
    assert notes_for(Department.DENTISTRY) == ("ot_dental_checklist", "ot_dental_note")
    assert "ot_operation_note" not in notes_for(Department.GASTROENTEROLOGY)
    assert "ot_operation_note" in notes_for(Department.ORTHOPEDICS)
    for key in notes_for(Department.DENTISTRY):
        assert REGISTRY[key].scope == "surgery"


def test_the_dental_checklist_gates_the_chair_and_asks_for_the_tooth():
    assert "ot_dental_checklist" in PRE_PROCEDURE_CHECKLISTS
    assert "tooth_confirmed" in PROTECTED_SECTIONS["ot_dental_checklist"]["checks"]
    checks = next(s for s in REGISTRY["ot_dental_checklist"].sections if s["key"] == "checks")
    assert not any(f["key"] == "fasting_confirmed" for f in checks["fields"])


@pytest.mark.parametrize("teeth,count", [("36", 1), ("36, 37", 2), ("Full mouth", 0), (None, 0)])
def test_a_per_tooth_price_is_charged_for_each_tooth(teeth, count):
    assert rules.tooth_count(teeth) == count


def test_the_dental_pad_has_a_tooth_chart_that_follows_the_patient():
    from app.pads.defaults import default_layout
    from app.pads.sections import validate_layout

    sections = default_layout("opd_visit", Department.DENTISTRY)
    keys = [s["key"] for s in sections]
    assert "tooth_chart" in keys and "treatment_plan" in keys
    assert "gi_symptoms" not in keys
    chart = next(s for s in sections if s["key"] == "tooth_chart")
    assert chart["carry_forward"]
    validate_layout(sections)
