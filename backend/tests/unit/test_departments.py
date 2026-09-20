"""The department registry.

The point of these tests is not that gastroenterology exists. It is that a
department which exists only halfway can no longer reach a patient: every
lookup raises, and the application refuses to start.
"""
import pytest

from app.ai.emergency import DEPARTMENT_FLAGS
from app.ai.session.memory import DEPARTMENT_SLOTS, slot_keys_for
from app.departments import (
    DepartmentNotConfigured,
    code_for,
    label_for,
    profile_for,
    require_department,
    validate_department_config,
)
from app.models.enums import Department

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("department", list(Department))
def test_every_department_is_fully_configured(department):
    """The check the application makes at startup, per department."""
    profile = profile_for(department)
    assert profile.label and profile.code
    assert profile.intake_guide.strip()
    assert profile.red_flag_guide.strip()
    assert len(profile.fallback_self_care) == 2
    assert department in DEPARTMENT_FLAGS
    assert department in DEPARTMENT_SLOTS


def test_startup_validation_passes_as_shipped():
    validate_department_config()


def test_department_codes_are_unique():
    """Two departments sharing a code would collide in prescription numbers."""
    codes = [code_for(d) for d in Department]
    assert len(codes) == len(set(codes))


def test_gastroenterology_is_its_own_department():
    assert label_for(Department.GASTROENTEROLOGY) == "Gastroenterology"
    assert code_for(Department.GASTROENTEROLOGY) == "GAS"
    guide = profile_for(Department.GASTROENTEROLOGY).intake_guide
    # It must not be handed another speciality's intake questions.
    assert "Gastroenterology" in guide
    assert "Menstrual history" not in guide


def test_require_department_raises_instead_of_defaulting():
    """The whole reason this helper exists, rather than dict.get(d, other)."""
    table = {Department.ORTHOPEDICS: "ortho content"}
    with pytest.raises(DepartmentNotConfigured) as exc:
        require_department(table, Department.GASTROENTEROLOGY, "intake guide")
    assert "gastroenterology" in str(exc.value)
    assert "intake guide" in str(exc.value)


def test_slot_checklist_is_department_specific():
    gastro = slot_keys_for(Department.GASTROENTEROLOGY)
    ortho = slot_keys_for(Department.ORTHOPEDICS)
    assert "bowel_habit" in gastro
    assert "bowel_habit" not in ortho
    # The common history is asked of everyone.
    assert {"chief_complaint", "allergies"} <= set(gastro)
