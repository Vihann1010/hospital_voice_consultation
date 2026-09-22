"""Endoscopy as a day procedure, on the theatre the hospital already has.

The module was written for an inpatient operation. Three things in it assumed
a bed: the checklist asked for an operation site to be marked, the bill was
posted to an admission, and the record was shaped like an operation note.
These tests pin the day-case path that runs beside it — not a second theatre,
the same one with the questions a scope actually raises.
"""
import pytest

from app.pads import sections as rules
from app.pads.defaults import PROTECTED_SECTIONS, REGISTRY, default_layout
from app.services.theatre_service import (
    DAY_PROCEDURE_CHECKLIST,
    PRE_OP_CHECKLIST,
    PRE_PROCEDURE_CHECKLISTS,
)
from app.theatre import rules as theatre_rules

pytestmark = pytest.mark.unit

CHECKLIST = "ot_day_procedure_checklist"
REPORT = "ot_endoscopy_report"


def _fields(document_type: str, section_key: str):
    section = next(s for s in default_layout(document_type) if s["key"] == section_key)
    return {spec["key"]: spec for spec in section["fields"]}


# ------------------------------------------------------------- the checklist


def test_the_day_checklist_does_not_ask_for_a_site_to_be_marked():
    """A gastroscopy has no site to mark.

    The surgical checklist makes site marking required, so the only way through
    it for a scope is to tick a box that is not true — which is how a ward
    learns that the checks are paperwork.
    """
    checks = _fields(CHECKLIST, "checks")
    assert "site_marked" not in checks
    assert _fields("ot_pre_op_checklist", "checks")["site_marked"]["required"] is True


def test_the_day_checklist_still_requires_identity_consent_and_fasting():
    checks = _fields(CHECKLIST, "checks")
    for key in ("identity_confirmed", "consent_signed", "fasting_confirmed"):
        assert checks[key]["required"] is True
    assert PROTECTED_SECTIONS[CHECKLIST]["checks"] == [
        "identity_confirmed", "consent_signed", "fasting_confirmed",
    ]


def test_the_day_checklist_asks_the_questions_sedation_raises():
    """Who is taking them home, and what did they stop taking."""
    checks = _fields(CHECKLIST, "checks")
    assert "escort_present" in checks
    assert "sedation_consent" in checks
    held = _fields(CHECKLIST, "medicines_held")
    assert "anticoagulant" in held
    assert "diabetes" in held
    assert "bowel_prep" in _fields(CHECKLIST, "preparation")


def test_either_checklist_admits_a_patient_to_theatre():
    """The door asks for consent and fasting, not for a particular form."""
    assert {PRE_OP_CHECKLIST, DAY_PROCEDURE_CHECKLIST} <= set(PRE_PROCEDURE_CHECKLISTS)


def test_the_checklist_is_the_nurses_and_the_report_is_the_doctors():
    assert REGISTRY[CHECKLIST].authority == "nursing"
    assert REGISTRY[REPORT].authority == "doctor"
    assert REGISTRY[CHECKLIST].scope == "surgery"
    assert REGISTRY[REPORT].scope == "surgery"


@pytest.mark.parametrize("document_type", [CHECKLIST, REPORT])
def test_the_new_layouts_are_valid(document_type):
    assert rules.validate_layout(default_layout(document_type))


# ---------------------------------------------------------------- the report


def test_the_endoscopy_report_records_what_a_scope_records():
    keys = {section["key"] for section in default_layout(REPORT)}
    assert {"indication", "conduct", "findings", "specimen", "diagnosis", "advice"} <= keys
    conduct = _fields(REPORT, "conduct")
    # Extent reached is the quality measure for a colonoscopy; without it the
    # report does not say whether the examination was complete.
    assert "extent" in conduct
    assert "sedation" in conduct
    assert "complications" in conduct


def test_the_biopsy_box_is_protected():
    """Signing with it ticked raises the histopathology order, so it must exist."""
    assert PROTECTED_SECTIONS[REPORT]["specimen"] == ["biopsy_taken"]


def test_the_report_carries_the_rapid_urease_result():
    """The one H. pylori test that happens at the scope itself."""
    assert "rapid_urease" in _fields(REPORT, "specimen")


def test_images_are_counted_here_and_filed_on_the_patient():
    """Rather than inventing a section kind the editor and the PDF must learn."""
    images = _fields(REPORT, "images")
    assert {"taken", "filed"} <= set(images)


# ------------------------------------------------------------ theatre rules


def test_a_scope_needs_no_incision_to_reach_completion():
    """Wheel in, wheel out. Incision and closure are for an operation."""
    assert theatre_rules.next_status("scheduled", "wheel_in") == "in_theatre"
    assert theatre_rules.next_status("in_theatre", "wheel_out") == "completed"


def test_not_applicable_is_a_real_answer_for_laterality():
    """A scope has no side, and a blank is how wrong-side surgery starts."""
    assert "Not applicable" in theatre_rules.LATERALITY


def test_sedation_and_local_are_offered_as_anaesthesia():
    """A fifteen-minute gastroscopy is not a general anaesthetic."""
    assert "Sedation" in theatre_rules.ANAESTHESIA_TYPES
    assert "Local" in theatre_rules.ANAESTHESIA_TYPES
