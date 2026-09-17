import pytest

from app.ai.pipeline.pipeline import fallback_patient_education
from app.models.enums import Department

pytestmark = pytest.mark.unit


def test_orthopedics_fallback_has_two_hindi_lines():
    fallback = fallback_patient_education(Department.ORTHOPEDICS)

    assert fallback.language == "hi"
    assert len(fallback.general_self_care) == 2
    assert all(any("\u0900" <= character <= "\u097f" for character in line)
               for line in fallback.general_self_care)


def test_gynecology_fallback_has_two_hindi_lines():
    fallback = fallback_patient_education(Department.GYNECOLOGY)

    assert fallback.language == "hi"
    assert len(fallback.general_self_care) == 2
    assert all(any("\u0900" <= character <= "\u097f" for character in line)
               for line in fallback.general_self_care)