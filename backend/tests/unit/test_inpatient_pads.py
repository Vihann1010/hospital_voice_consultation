"""Inpatient documents on the Visit Pad, and who may write them.

Pure data: the document registry, what is copied from the admission, how a
signed document is flattened for the discharge draft, and the nurse role's
permissions. Nothing here touches a database.
"""
import pytest

from app.core.permissions import Permission, has_permission
from app.models.enums import UserRole
from app.pads import sections as rules
from app.pads.defaults import REGISTRY, default_layout

pytestmark = pytest.mark.unit

INPATIENT = [key for key, spec in REGISTRY.items() if spec.scope == "admission"]


# -------------------------------------------------------------- registry
def test_the_five_inpatient_documents_exist():
    assert set(INPATIENT) == {
        "ipd_admission_note", "ipd_progress_note", "ipd_nursing_assessment",
        "ipd_nursing_note", "ipd_discharge_summary",
    }


@pytest.mark.parametrize("key", INPATIENT)
def test_every_inpatient_layout_is_valid(key):
    assert rules.validate_layout(default_layout(key))


def test_nursing_documents_are_the_nurses():
    assert REGISTRY["ipd_nursing_assessment"].authority == "nursing"
    assert REGISTRY["ipd_nursing_note"].authority == "nursing"
    assert REGISTRY["ipd_progress_note"].authority == "doctor"
    assert REGISTRY["ipd_discharge_summary"].authority == "doctor"


def test_notes_are_many_and_summaries_are_one():
    assert REGISTRY["ipd_progress_note"].many and REGISTRY["ipd_nursing_note"].many
    assert not REGISTRY["ipd_discharge_summary"].many
    assert not REGISTRY["ipd_admission_note"].many
    assert not REGISTRY["ipd_nursing_assessment"].many


def test_no_inpatient_layout_uses_intake_ai_sections():
    # The intake conversation is an OPD thing. An inpatient document drafted
    # from it would be drafted from the wrong visit.
    for key in INPATIENT:
        assert all(section["kind"] != "ai" for section in default_layout(key))


def test_a_progress_note_carries_assessment_and_plan_forward():
    carried = {s["key"] for s in rules.validate_layout(default_layout("ipd_progress_note"))
               if s["carry_forward"]}
    assert carried == {"assessment", "plan"}


def test_a_nursing_note_cannot_be_signed_without_a_shift():
    shift = next(s for s in default_layout("ipd_nursing_note") if s["key"] == "shift")
    assert shift["fields"][0]["required"] is True


def test_prefill_is_refused_on_a_fields_section():
    with pytest.raises(rules.LayoutError, match="filled from the admission"):
        rules.validate_layout([{
            "key": "v", "title": "V", "kind": "fields", "prefill_from": "allergies",
            "fields": [{"key": "a", "label": "A"}],
        }])


# ------------------------------------------------------------------ prefill
def test_admission_facts_are_copied_into_a_new_document():
    layout = rules.validate_layout(default_layout("ipd_admission_note"))
    values, provenance = rules.draft_from_record(layout, {
        "reason_for_admission": "Fall at home, unable to bear weight",
        "provisional_diagnosis": "Fracture neck of femur, right",
        "final_diagnosis": None,
        "allergies": ["Penicillin", "  "],
    })
    assert values["presenting_complaint"]["items"] == ["Fall at home, unable to bear weight"]
    assert values["provisional_diagnosis"]["items"] == ["Fracture neck of femur, right"]
    assert values["allergies"]["items"] == ["Penicillin"]
    assert provenance["allergies"] == {"source": "admission:allergies"}


def test_an_empty_allergy_list_stays_empty_rather_than_no_known_allergies():
    layout = rules.validate_layout(default_layout("ipd_nursing_assessment"))
    values, provenance = rules.draft_from_record(layout, {"allergies": []})
    assert "allergies" not in values and "allergies" not in provenance


def test_a_provisional_diagnosis_is_not_promoted_into_the_final_one():
    layout = rules.validate_layout(default_layout("ipd_discharge_summary"))
    values, _ = rules.draft_from_record(layout, {
        "provisional_diagnosis": "Suspected fracture", "final_diagnosis": None,
    })
    assert "final_diagnosis" not in values


def test_text_sections_receive_prose_not_a_list():
    layout = rules.validate_layout(default_layout("ipd_discharge_summary"))
    values, _ = rules.draft_from_record(layout, {"reason_for_admission": "Chest pain"})
    assert values["presenting_complaint"] == {"text": "Chest pain"}


# ------------------------------------------------------------------ as_text
def test_a_signed_note_flattens_into_readable_lines():
    layout = rules.validate_layout(default_layout("ipd_nursing_assessment"))
    text = rules.as_text(layout, {
        "vitals": {"fields": {"bp": "130/80", "pulse": 88, "spo2": None}},
        "fall_risk": {"fields": {"risk": "High", "precautions": ["Side rails up", "Call bell within reach"]}},
        "arrival": {"fields": {"id_band": True}},
        "valuables": {"text": "Phone and wallet to son"},
    })
    assert "Vitals on admission: BP 130/80 mmHg; Pulse 88 /min" in text
    assert "Fall risk: Risk High; Precautions Side rails up, Call bell within reach" in text
    assert "ID band applied yes" in text
    assert "Valuables and belongings: Phone and wallet to son" in text
    assert "SpO2" not in text


# -------------------------------------------------------------- nurse role
def test_a_nurse_charts_and_writes_nursing_documents():
    assert has_permission(UserRole.NURSE, Permission.WARD_CHART)
    assert has_permission(UserRole.NURSE, Permission.NURSING_DOCUMENT)
    assert has_permission(UserRole.NURSE, Permission.PATIENT_READ)
    assert has_permission(UserRole.NURSE, Permission.CONSULTATION_READ)


@pytest.mark.parametrize("permission", [
    Permission.CLINICAL_DOCUMENT_WRITE,
    Permission.CLINICAL_DOCUMENT_SIGN,
    Permission.PRESCRIPTION_CREATE,
    Permission.CONSULTATION_REVIEW,
    Permission.ORDER_CREATE,
    Permission.PAYMENT_COLLECT,
    Permission.INVOICE_CREATE,
    Permission.REFUND_ISSUE,
    Permission.FINANCE_READ,
])
def test_a_nurse_holds_no_clinical_or_money_authority(permission):
    assert not has_permission(UserRole.NURSE, permission)


def test_nursing_documents_belong_to_nurses_alone():
    for role in (UserRole.DOCTOR, UserRole.SUPERVISOR, UserRole.RECEPTION, UserRole.MANAGER):
        assert not has_permission(role, Permission.NURSING_DOCUMENT)


def test_a_manager_no_longer_charts_on_the_ward():
    assert not has_permission(UserRole.MANAGER, Permission.WARD_CHART)


def test_the_existing_ward_accounts_keep_charting():
    for role in (UserRole.DOCTOR, UserRole.SUPERVISOR, UserRole.RECEPTION):
        assert has_permission(role, Permission.WARD_CHART)
