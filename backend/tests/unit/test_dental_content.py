"""Dentistry clinical content, and the same sign-off gate as gastroenterology.

The dental medicines and templates were drafted by whoever added the
department, not by a dentist, so they are withheld until one signs them off.
The general antibiotics and analgesics a dentist also uses are not dental
content and stay available throughout.
"""
import pytest

from app.core.config import settings
from app.investigations import catalog
from app.models.enums import Department, InvestigationCategory
from app.prescriptions import formulary

pytestmark = pytest.mark.unit

DENTAL = Department.DENTISTRY
GASTRO = Department.GASTROENTEROLOGY
DENTAL_CODES = ("AMOX_DENTAL", "METRO_DENTAL", "CLINDAMYCIN", "KETOROLAC", "CHX_MW",
                "BENZYDAMINE_MW", "LIGNO_GEL", "TRIAM_PASTE", "CLOTRIM_PAINT", "KNO3_PASTE")


@pytest.fixture
def approved_dental(monkeypatch):
    monkeypatch.setattr(settings, "APPROVED_FORMULARY", "orthopedics,gynecology,dentistry")


def test_every_dental_medicine_is_drafted_and_withheld():
    for code in DENTAL_CODES:
        item = formulary.get_including_unapproved(code)
        assert item is not None and item.provisional, code
        assert formulary.get(code) is None, f"{code} is reachable before sign-off"


def test_dental_templates_are_withheld_until_signed_off(approved_dental):
    assert formulary.search_templates("toothache", department=DENTAL)


def test_no_dental_template_is_offered_before_sign_off():
    assert formulary.search_templates("toothache", department=DENTAL) == []


def test_the_dentist_keeps_the_general_medicines_meanwhile():
    names = {m.code for m in formulary.search(department=DENTAL, limit=500)}
    assert {"PARA", "BRUFEN", "AUGMENTIN", "METROGYL"} <= names


def test_dental_templates_only_name_medicines_that_exist():
    for template in formulary.MEDICINE_TEMPLATES:
        if template.department is DENTAL:
            assert template.provisional
            for code in template.medicine_codes:
                assert formulary.get_including_unapproved(code), (template.disease_name, code)


def test_pulpitis_is_not_treated_with_antibiotics():
    """The commonest dental prescribing error, so the template must not make it."""
    template = next(t for t in formulary.MEDICINE_TEMPLATES
                    if t.disease_name.startswith("Toothache"))
    for code in template.medicine_codes:
        assert "antibiotic" not in formulary.get_including_unapproved(code).category.lower()


def test_dental_medicines_are_not_offered_to_the_gastroenterologist(approved_dental):
    names = {m.code for m in formulary.search(department=GASTRO, limit=500)}
    assert "CHX_MW" not in names


@pytest.mark.parametrize(
    "first,second",
    [("KETOROLAC", "BRUFEN"), ("METRO_DENTAL", "WARFARIN")],
)
def test_dental_interactions_are_caught(first, second):
    from app.prescriptions.safety import check_interactions

    names = []
    for code in (first, second):
        item = formulary.get_including_unapproved(code)
        names.append({"name": item.name if item else code.title(), "formulary_code": code})
    assert check_interactions(names)


def test_the_dentist_can_order_dental_radiographs():
    codes = {item.code for item in catalog.search(department=DENTAL, limit=500)}
    for expected in ("DENT_IOPA", "DENT_OPG", "DENT_CBCT", "CBC", "COAG"):
        assert expected in codes
    assert catalog.get("DENT_OPG").category is InvestigationCategory.DENTAL


def test_dental_radiographs_do_not_appear_for_the_gastroenterologist():
    codes = {item.code for item in catalog.search(department=GASTRO, limit=500)}
    assert "DENT_OPG" not in codes


def test_dental_panels_expand_to_real_codes():
    for panel in ("PANEL_DENTAL_SURGERY", "PANEL_IMPLANT"):
        assert catalog.expand_codes([panel])
