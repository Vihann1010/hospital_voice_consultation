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
