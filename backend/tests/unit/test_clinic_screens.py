"""What the three screens are offered: departments, and the doctor's pad.

A single-speciality clinic should not ask a patient at the door to choose
between three specialities, two of which are not in the building. And the
doctor's pad should open in the shape that speciality works in, without
anybody having to build it first.
"""
import pytest

from app.core.config import Settings, settings
from app.models.enums import Department
from app.pads import sections as rules
from app.pads.defaults import DEPARTMENT_LAYOUTS, default_layout

pytestmark = pytest.mark.unit

GASTRO = Department.GASTROENTEROLOGY


# ------------------------------------------------ what the screens offer


def test_an_unset_site_offers_every_department():
    """A hospital that configures nothing keeps the screens it has."""
    assert Settings(ENABLED_DEPARTMENTS="").enabled_departments == list(Department)


def test_a_single_speciality_clinic_offers_one():
    config = Settings(ENABLED_DEPARTMENTS="gastroenterology")
    assert config.enabled_departments == [GASTRO]


def test_the_list_keeps_enum_order_whatever_order_it_is_written_in():
    """So the screens list them the same way every time."""
    config = Settings(ENABLED_DEPARTMENTS="gastroenterology, orthopedics")
    assert config.enabled_departments == [Department.ORTHOPEDICS, GASTRO]


def test_a_name_that_is_not_a_department_is_refused():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(ENABLED_DEPARTMENTS="gastroenterology,urology")


def test_the_configured_default_is_one_the_site_runs():
    """Otherwise the registration screen starts on a department it cannot offer."""
    assert settings.default_department in settings.enabled_departments


# ------------------------------------------------------- the doctor's pad


def test_the_gastro_pad_opens_in_the_shape_gastroenterology_works_in():
    keys = [section["key"] for section in default_layout("opd_visit", GASTRO)]
    assert "gi_symptoms" in keys
    assert "endoscopy_history" in keys
    assert "diet_advice" in keys
    # Still the OPD visit pad, not a fork of it.
    assert {"intake_summary", "complaints", "diagnosis", "follow_up"} <= set(keys)


def test_the_gi_review_asks_the_four_questions_every_visit_repeats():
    section = next(
        s for s in default_layout("opd_visit", GASTRO) if s["key"] == "gi_symptoms"
    )
    keys = {field["key"] for field in section["fields"]}
    assert keys == {"appetite", "weight_change", "bowel_habit", "bleeding"}


def test_what_the_last_scope_showed_carries_forward():
    """It is the context for every visit after it."""
    section = next(
        s for s in default_layout("opd_visit", GASTRO) if s["key"] == "endoscopy_history"
    )
    assert section["carry_forward"] is True


def test_the_other_departments_are_untouched():
    generic = [s["key"] for s in default_layout("opd_visit")]
    ortho = [s["key"] for s in default_layout("opd_visit", Department.ORTHOPEDICS)]
    assert ortho == generic
    assert "gi_symptoms" not in generic


@pytest.mark.parametrize("key", sorted(DEPARTMENT_LAYOUTS))
def test_every_department_layout_is_valid(key):
    """It goes through the same validation as one an administrator saves."""
    document_type, department = key
    assert rules.validate_layout(default_layout(document_type, department))


def test_a_department_layout_names_a_real_document_type():
    from app.pads.defaults import REGISTRY

    for document_type, department in DEPARTMENT_LAYOUTS:
        assert document_type in REGISTRY
        assert isinstance(department, Department)


def test_the_default_is_a_fresh_copy_each_time():
    """A caller that edits what it is given must not change it for everyone."""
    first = default_layout("opd_visit", GASTRO)
    first[0]["title"] = "Mutated"
    assert default_layout("opd_visit", GASTRO)[0]["title"] != "Mutated"
