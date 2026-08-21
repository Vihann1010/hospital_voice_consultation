"""Reference data integrity: investigation catalog and prescribing formulary."""
import pytest

from app.investigations import catalog
from app.investigations.reference_ranges import QUALITATIVE_EXPECTED, REFERENCE_RANGES
from app.models.enums import Department, InvestigationCategory
from app.prescriptions import formulary

pytestmark = pytest.mark.unit


def test_every_category_has_investigations():
    for category in InvestigationCategory:
        assert catalog.search(None, category=category), f"{category.value} is empty"


def test_catalog_codes_are_unique():
    codes = [item.code for item in catalog.CATALOG]
    assert len(codes) == len(set(codes))


def test_panel_members_all_resolve():
    for panel in catalog.PANELS:
        for member in panel.members:
            assert member in catalog.CATALOG_BY_CODE, f"{panel.code} -> {member}"


def test_declared_analytes_have_reference_data():
    for item in catalog.CATALOG:
        for analyte in item.analytes:
            assert analyte in REFERENCE_RANGES or analyte in QUALITATIVE_EXPECTED


def test_panel_expansion_deduplicates():
    items = catalog.expand_codes(["PANEL_PCOS", "CBC", "PANEL_PCOS"])
    codes = [item.code for item in items]
    assert len(codes) == len(set(codes))


def test_department_scoping_is_honoured():
    gynecology = catalog.search(None, department=Department.GYNECOLOGY, limit=500)
    orthopedics = catalog.search(None, department=Department.ORTHOPEDICS, limit=500)
    assert not any(item.code == "XR_KNEE" for item in gynecology)
    assert not any(item.code == "GYN_PAP" for item in orthopedics)
    assert any(item.code == "CBC" for item in gynecology)
    assert any(item.code == "CBC" for item in orthopedics)


@pytest.mark.parametrize(
    "query,expected_code",
    [("knee", "XR_KNEE"), ("ca 125", "TM_CA125"), ("pap", "GYN_PAP"), ("dexa", "DEXA_SPINE_HIP")],
)
def test_catalog_search_finds_expected(query, expected_code):
    assert any(item.code == expected_code for item in catalog.search(query, limit=10))


def test_formulary_codes_are_unique():
    codes = [item.code for item in formulary.FORMULARY]
    assert len(codes) == len(set(codes))


@pytest.mark.parametrize(
    "spoken,expected",
    [("Paracetamol", "PARA"), ("Tab Dolo 650", "DOLO"),
     ("Pantoprazole", "PAN"), ("Shelcal 500", "SHELCAL")],
)
def test_formulary_name_matching(spoken, expected):
    matched = formulary.match_by_name(spoken)
    assert matched is not None and matched.code == expected


def test_unknown_medicine_returns_nothing():
    assert formulary.match_by_name("Nonexistent Drug Xyz") is None
