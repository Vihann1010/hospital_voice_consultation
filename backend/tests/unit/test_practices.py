"""Two practices under one roof, each its own business."""
import pytest

from app import practices
from app.billing import identifiers
from app.core.config import settings
from app.models.enums import Department

pytestmark = pytest.mark.unit

TWO = "CNG=CN Gastrocare:gastroenterology;SMD=Smile Dental:dentistry"


@pytest.fixture
def two_practices(monkeypatch):
    monkeypatch.setattr(settings, "PRACTICES", TWO)


def test_a_site_that_sets_nothing_is_one_practice(monkeypatch):
    monkeypatch.setattr(settings, "PRACTICES", "")
    only = practices.all_practices()
    assert len(only) == 1 and only[0].prefix == settings.DOCUMENT_PREFIX
    assert practices.for_department(Department.DENTISTRY) is not None


def test_each_department_belongs_to_its_practice(two_practices):
    assert practices.for_department(Department.DENTISTRY).name == "Smile Dental"
    assert practices.for_department(Department.GASTROENTEROLOGY).prefix == "CNG"
    assert practices.default_practice().prefix == "CNG"


def test_the_default_practice_keeps_its_old_counters(two_practices):
    cng, smd = practices.all_practices()
    assert practices.counter_scope("invoice", cng) == "invoice"
    assert practices.counter_scope("invoice", smd) == "invoice:SMD"


def test_each_practice_numbers_its_own_documents(two_practices):
    assert identifiers.build_uhid(1, prefix="SMD").startswith("SMD")
    assert identifiers.build_invoice_number(7, prefix="SMD").startswith("SMD/")
    assert identifiers.build_receipt_number(7, prefix="SMD").startswith("SMD-RCP/")
    assert identifiers.build_receipt_number(7, prefix="CNG").startswith("RCP/")


def test_both_practices_uhids_are_recognised(two_practices):
    assert identifiers.is_valid_uhid(identifiers.build_uhid(5, prefix="SMD"))
    assert identifiers.is_valid_uhid(identifiers.build_uhid(5, prefix="CNG"))
    assert not identifiers.is_valid_uhid(identifiers.build_uhid(5, prefix="XYZ"))


def test_the_bill_carries_its_practice_name(two_practices):
    assert settings.brand_for(Department.DENTISTRY) == "Smile Dental"


@pytest.mark.parametrize("raw", [
    "SM=Smile Dental:dentistry",                                    # two letters
    "SMD=Smile Dental",                                             # no department
    "SMD=Smile Dental:dental",                                      # not a department
    "SMD=A:dentistry;SMD=B:gastroenterology",                        # letters repeated
    "CNG=A:gastroenterology;SMD=B:gastroenterology",                  # department twice
])
def test_an_incoherent_practice_list_is_refused(raw):
    with pytest.raises(practices.PracticeConfigError):
        practices.parse(raw)
