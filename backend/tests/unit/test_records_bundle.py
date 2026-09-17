"""The records bundle: filing order and date filtering."""
from datetime import date

import pytest

from app.mrd.bundle import SECTIONS, Item, in_range, section_for, sort_key

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("document_type, section", [
    ("consent_surgical", "Consent"),
    ("lama_form", "Consent"),
    ("cert_medical_leave", "Certificates"),
    ("radiology_report", "Investigations"),
    ("ot_operation_note", "Theatre"),
    ("ipd_progress_note", "Doctor's notes"),
    ("ipd_nursing_note", "Nursing"),
    ("ipd_discharge_summary", "Discharge"),
])
def test_each_document_is_filed_in_its_section(document_type, section):
    assert section_for(document_type) == section


def test_the_file_opens_with_the_cover_and_ends_with_the_bill():
    items = [
        Item("invoice:1", "Billing", "Final bill", "invoice", "2026-09-10"),
        Item("pad:2", "Doctor's notes", "Progress note", "pad", "2026-09-05"),
        Item("pad:3", "Doctor's notes", "Admission note", "pad", "2026-09-01"),
        Item("cover", "Admission record", "Admission record", "cover", "2026-09-01"),
        Item("pad:4", "Consent", "General consent", "pad", "2026-09-01"),
    ]
    ordered = [item.key for item in sorted(items, key=sort_key)]
    assert ordered == ["cover", "pad:4", "pad:3", "pad:2", "invoice:1"]
    assert SECTIONS[0] == "Admission record" and SECTIONS[-1] == "Billing"


def test_date_range_is_inclusive_and_open_ended():
    assert in_range("2026-09-05", date(2026, 9, 5), date(2026, 9, 5))
    assert not in_range("2026-09-04", date(2026, 9, 5), None)
    assert in_range("2026-09-30", date(2026, 9, 5), None)
    assert not in_range("2026-09-06", None, date(2026, 9, 5))
    assert in_range(None, date(2026, 9, 5), date(2026, 9, 6))
