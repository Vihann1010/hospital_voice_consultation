import pytest

from app.models.enums import Department
from app.prescriptions.formulary import search_templates

pytestmark = pytest.mark.unit


def test_diagnosis_template_matches_olecranon_fracture():
    templates = search_templates(
        "comminuted fracture olecranon right elbow with tendon injury",
        department=Department.ORTHOPEDICS,
    )

    assert templates
    assert templates[0].disease_name == "Olecranon fracture with tendon injury"
    assert templates[0].medicine_codes


def test_templates_are_department_scoped():
    templates = search_templates("period pain", department=Department.ORTHOPEDICS)

    assert templates == []