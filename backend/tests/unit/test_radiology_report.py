"""Radiology reports: what may be signed, and what a report starts with."""
from datetime import date

import pytest

from app.pads import forms
from app.pads import sections as rules
from app.pads.defaults import REGISTRY, default_layout

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 13)


def study(**fields):
    return {"study": {"fields": fields}}


def test_radiology_report_is_a_numbered_doctor_document():
    spec = REGISTRY["radiology_report"]
    assert (spec.scope, spec.authority, spec.family) == ("patient", "doctor", "radiology")
    assert forms.SERIAL_PREFIX["radiology"] == "RR"
    assert rules.validate_layout(default_layout("radiology_report"))


def test_a_report_needs_findings_and_an_impression():
    problems = forms.check("radiology_report", study(study_name="X-Ray Chest PA", study_date="2026-09-13"),
                           today=TODAY)
    assert problems == ["Write the findings", "Give an impression"]
    complete = {**study(study_name="X-Ray Chest PA", study_date="2026-09-13"),
                "findings": {"text": "Lung fields are clear."}, "impression": {"items": ["Normal study"]}}
    assert forms.check("radiology_report", complete, today=TODAY) == []


def test_a_study_dated_tomorrow_is_refused():
    values = {**study(study_name="USG Abdomen", study_date="2026-09-14"),
              "findings": {"text": "Normal."}, "impression": {"items": ["Normal"]}}
    assert forms.check("radiology_report", values, today=TODAY) == ["The study date is in the future"]


def test_a_report_starts_from_its_order():
    values = forms.prefill("radiology_report", today=TODAY, order_item={
        "name": "X-Ray Knee (AP & Lateral)", "site": "Left knee", "indication": "Twisting injury"})
    assert values == {"study": {"fields": {
        "study_name": "X-Ray Knee (AP & Lateral)", "site": "Left knee",
        "indication": "Twisting injury", "study_date": "2026-09-13"}}}


def test_imaging_categories():
    assert forms.IMAGING_CATEGORIES == {"xray", "mri", "ct", "ultrasound", "dexa"}
