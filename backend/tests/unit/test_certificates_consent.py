"""Certificates and consent forms: what may be signed, and what gets printed."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.pads import forms
from app.pads import sections as rules
from app.pads.defaults import REGISTRY, default_layout

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 13)
FAMILY = {key: spec for key, spec in REGISTRY.items() if spec.family}


def cert(**values):
    return {"certificate": {"fields": values}}


def consent(**given):
    return {"consent_by": {"fields": given}}


def adult_patient(**extra):
    base = dict(name="Sourav Kumar", title="Mr.", age=20, gender=SimpleNamespace(value="male"),
                uhid="SAT26AAAAAP", guardian_name=None, guardian_relation=None)
    base.update(extra)
    return SimpleNamespace(**base)


def test_eight_forms_are_registered_with_their_families():
    assert {k for k, s in FAMILY.items() if s.family == "certificate"} == {
        "cert_medical_leave", "cert_fitness", "cert_hospitalisation"}
    assert {k for k, s in FAMILY.items() if s.family == "consent"} == {
        "consent_general", "consent_surgical", "consent_blood_transfusion", "consent_high_risk", "lama_form"}
    assert all(spec.scope == "patient" and spec.authority == "doctor" for spec in FAMILY.values())
    assert REGISTRY["cert_hospitalisation"].requires == "admission"
    assert REGISTRY["lama_form"].requires == "admission"


@pytest.mark.parametrize("key", sorted(FAMILY))
def test_every_form_layout_is_valid(key):
    assert rules.validate_layout(default_layout(key))


@pytest.mark.parametrize("key", sorted(k for k, s in FAMILY.items() if s.family == "consent"))
def test_every_consent_has_english_and_hindi_wording_of_equal_length(key):
    wording = forms.STATEMENTS[key]
    assert wording["en"] and len(wording["en"]) == len(wording["hi"])
    assert all(any("ऀ" <= ch <= "ॿ" for ch in line) for line in wording["hi"])
    assert key in forms.TITLE_HI


def test_rest_that_ends_before_it_starts_is_refused():
    problems = forms.check("cert_medical_leave", cert(examined_on="2026-09-13", rest_from="2026-09-13",
                                                      rest_to="2026-09-10"), today=TODAY)
    assert problems == ["Rest cannot end before it starts"]


def test_rest_before_the_examination_is_refused():
    problems = forms.check("cert_medical_leave", cert(examined_on="2026-09-13", rest_from="2026-09-09",
                                                      rest_to="2026-09-15"), today=TODAY)
    assert len(problems) == 1 and "before the patient was examined" in problems[0]


def test_an_examination_dated_tomorrow_is_refused():
    problems = forms.check("cert_fitness", cert(examined_on="2026-09-14", fit_from="2026-09-14",
                                                fit_for="Resume duty"), today=TODAY)
    assert problems == ["The examination date is in the future"]


def test_fit_for_other_needs_saying_what():
    problems = forms.check("cert_fitness", cert(examined_on="2026-09-13", fit_from="2026-09-13",
                                                fit_for="Other"), today=TODAY)
    assert problems == ["Say what the patient is fit for"]


def test_hospitalisation_dates_must_match_the_admission():
    record = {"admitted_on": date(2026, 9, 1), "discharged_on": None}
    assert forms.check("cert_hospitalisation", cert(admitted_on="2026-09-01"), today=TODAY,
                       admission=record) == []
    wrong = forms.check("cert_hospitalisation", cert(admitted_on="2026-08-30", discharged_on="2026-09-05"),
                        today=TODAY, admission=record)
    assert any("must match the admission record (01 Sep 2026)" in p for p in wrong)
    assert any("not been discharged" in p for p in wrong)
    assert forms.check("cert_hospitalisation", cert(admitted_on="2026-09-01"), today=TODAY,
                       admission=None) == ["A hospitalisation certificate must be issued from the admission"]


def test_a_minor_cannot_consent_for_themselves():
    problems = forms.check("consent_general", consent(consent_given_by="Patient", language="Hindi",
                                                      witness_name="Ram"), today=TODAY, patient_age=16)
    assert problems == ["The patient is 16 — under 18, so a parent or guardian must give consent"]


def test_a_guardian_needs_a_name_a_relation_and_a_reason():
    problems = forms.check("consent_general", consent(consent_given_by=forms.GUARDIAN, language="Hindi",
                                                      witness_name="Ram"), today=TODAY, patient_age=40)
    assert problems == ["Give the guardian's name", "Give the guardian's relation to the patient",
                        "Say why the patient is not consenting personally"]


def test_surgical_consent_needs_risks_and_alternatives():
    values = {**consent(consent_given_by="Patient", language="English", witness_name="Sita")}
    problems = forms.check("consent_surgical", values, today=TODAY, patient_age=40)
    assert problems == ["List the specific risks that were explained",
                        "Record the alternatives that were explained"]
    values.update({"risks": {"items": ["Infection"]}, "alternatives": {"text": "Physiotherapy"}})
    assert forms.check("consent_surgical", values, today=TODAY, patient_age=40) == []


def test_medical_leave_wording_is_built_from_the_fields():
    lines = forms.certificate_paragraphs(
        "cert_medical_leave",
        cert(examined_on="2026-09-13", diagnosis="Acute gastroenteritis", rest_from="2026-09-13",
             rest_to="2026-09-15", submitted_to="ABC Pvt Ltd"),
        patient=adult_patient(), issued_on=TODAY,
    )
    assert lines[0] == (
        "This is to certify that Mr. Sourav Kumar, aged 20 years, Male, UHID SAT26AAAAAP, was examined by "
        "me on 13 Sep 2026. The patient is suffering from Acute gastroenteritis and has been advised rest "
        "from 13 Sep 2026 to 15 Sep 2026, both days inclusive — 3 days."
    )
    assert lines[-1] == "Issued at the patient's request for submission to ABC Pvt Ltd."


def test_hospitalisation_wording_for_a_patient_still_admitted():
    lines = forms.certificate_paragraphs(
        "cert_hospitalisation", cert(admitted_on="2026-09-01", diagnosis="Fracture neck of femur"),
        patient=adult_patient(), issued_on=TODAY, ip_number="IP26-00002",
    )
    assert "admitted to this hospital on 01 Sep 2026 under IP number IP26-00002 and remains admitted " \
           "as of 13 Sep 2026, for Fracture neck of femur." in lines[0]


def test_surgical_consent_starts_from_the_booking_but_not_from_a_guess_about_who_consents():
    values = forms.prefill("consent_surgical", today=TODAY, surgery={
        "procedure": "Total knee replacement", "side": "Left", "diagnosis": "OA knee",
        "surgeon": "Dr. A K Agarwal", "anaesthesia": "Spinal"})
    assert values["details"]["fields"]["side"] == "Left"
    assert "consent_by" not in values


def test_serial_prefixes():
    assert forms.SERIAL_PREFIX == {"certificate": "MC", "consent": "CN", "radiology": "RR"}
