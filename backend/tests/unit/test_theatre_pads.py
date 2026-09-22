"""Theatre notes on the Visit Pad, and who owns them."""
import pytest

from app.core.permissions import Permission, has_permission
from app.models.enums import UserRole
from app.pads import sections as rules
from app.pads.defaults import REGISTRY, default_layout

pytestmark = pytest.mark.unit

THEATRE = [key for key, spec in REGISTRY.items() if spec.scope == "surgery"]


def test_the_theatre_notes_exist():
    assert set(THEATRE) == {
        "ot_pre_op_checklist", "ot_pre_anaesthetic", "ot_operation_note", "ot_post_op_orders",
        # A day-case clinic runs the same theatre with a checklist that asks
        # about an escort rather than a marked site, and a report shaped like
        # an endoscopy rather than an operation.
        "ot_day_procedure_checklist", "ot_endoscopy_report",
        # A dental chair: the tooth confirmed before anything is done, and a
        # note of what was done to which tooth.
        "ot_dental_checklist", "ot_dental_note",
    }


@pytest.mark.parametrize("key", THEATRE)
def test_every_theatre_layout_is_valid(key):
    assert rules.validate_layout(default_layout(key))


def test_the_pre_op_checklist_is_the_nurses_and_the_rest_are_doctors():
    assert REGISTRY["ot_pre_op_checklist"].authority == "nursing"
    assert REGISTRY["ot_day_procedure_checklist"].authority == "nursing"
    assert REGISTRY["ot_endoscopy_report"].authority == "doctor"
    for key in ("ot_pre_anaesthetic", "ot_operation_note", "ot_post_op_orders"):
        assert REGISTRY[key].authority == "doctor"


def test_consent_site_and_identity_are_required_on_the_checklist():
    checks = next(s for s in default_layout("ot_pre_op_checklist") if s["key"] == "checks")
    required = {field["key"] for field in checks["fields"] if field.get("required")}
    assert required == {"identity_confirmed", "consent_signed", "site_marked"}


def test_the_booked_side_is_copied_into_the_operation_note():
    layout = rules.validate_layout(default_layout("ot_operation_note"))
    values, provenance = rules.draft_from_record(layout, {
        "procedure": "Total knee replacement — Left",
        "diagnosis": "Osteoarthritis knee",
        "team": ["Surgeon: Dr. A K Agarwal", "Anaesthesia: Spinal"],
    })
    assert values["procedure"] == {"text": "Total knee replacement — Left"}
    assert values["team"]["text"] == "Surgeon: Dr. A K Agarwal\nAnaesthesia: Spinal"
    assert values["pre_op_diagnosis"] == {"items": ["Osteoarthritis knee"]}
    assert provenance["procedure"] == {"source": "admission:procedure"}


@pytest.mark.parametrize("role, schedule, record", [
    (UserRole.DOCTOR, True, True),
    (UserRole.NURSE, False, True),
    (UserRole.RECEPTION, False, False),
    (UserRole.SUPERVISOR, False, False),
    (UserRole.MANAGER, False, False),
])
def test_who_may_book_and_who_may_record_theatre_times(role, schedule, record):
    assert has_permission(role, Permission.THEATRE_SCHEDULE) is schedule
    assert has_permission(role, Permission.THEATRE_RECORD) is record
