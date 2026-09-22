"""The platform mark is a setting, and a typo in it is loud."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.unit


def test_platform_brand_defaults_to_none():
    assert Settings(_env_file=None).PLATFORM_BRAND == "none"


def test_platform_brand_reads_medicos_case_insensitively():
    assert Settings(_env_file=None, PLATFORM_BRAND=" MedicOS ").PLATFORM_BRAND == "medicos"


def test_platform_brand_rejects_anything_else():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, PLATFORM_BRAND="medicus")


def test_greeting_carries_this_sites_name():
    s = Settings(_env_file=None, HOSPITAL_NAME="CN Gastrocare",
                 HOSPITAL_NAME_SPOKEN="सी एन गैस्ट्रोकेयर",
                 GREETING_TEXT="नमस्ते, {hospital} की सहायिका।")
    assert s.greeting == "नमस्ते, सी एन गैस्ट्रोकेयर की सहायिका।"


def test_default_greeting_names_no_hospital_of_its_own():
    """The shipped sentence is a template; the name comes from settings."""
    s = Settings(_env_file=None, HOSPITAL_NAME="CN Gastrocare")
    assert "{hospital}" in s.GREETING_TEXT
    assert "सत्या" not in s.greeting
    assert "CN Gastrocare" in s.greeting


from app.models.enums import Department  # noqa: E402

TWO_PRACTICES = dict(
    _env_file=None,
    HOSPITAL_NAME="CN Gastrocare & Smile Dental",
    DEPARTMENT_BRANDS="gastroenterology=CN Gastrocare;dentistry=Smile Dental",
    DEPARTMENT_BRANDS_SPOKEN="dentistry=स्माइल डेंटल",
    GREETING_TEXT="नमस्ते, {hospital} की सहायिका।",
)


def test_each_department_has_its_own_practice_name():
    s = Settings(**TWO_PRACTICES)
    assert s.brand_for(Department.DENTISTRY) == "Smile Dental"
    assert s.brand_for(Department.GASTROENTEROLOGY) == "CN Gastrocare"


def test_a_bill_with_no_department_is_the_sites():
    s = Settings(**TWO_PRACTICES)
    assert s.brand_for(None) == "CN Gastrocare & Smile Dental"
    assert s.brand_for(Department.ORTHOPEDICS) == "CN Gastrocare & Smile Dental"


def test_a_dental_patient_is_greeted_by_smile_dental():
    s = Settings(**TWO_PRACTICES)
    assert s.greeting_for(Department.DENTISTRY) == "नमस्ते, स्माइल डेंटल की सहायिका।"
    # No spoken form given for gastro: the written name is said instead.
    assert "CN Gastrocare की" in s.greeting_for(Department.GASTROENTEROLOGY)


@pytest.mark.parametrize("raw", ["dentistry", "dentistry=", "dental=Smile Dental"])
def test_a_malformed_brand_list_is_refused(raw):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DEPARTMENT_BRANDS=raw)
