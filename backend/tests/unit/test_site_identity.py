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
