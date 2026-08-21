"""Layer-1 emergency detection.

Both directions matter equally: a missed red flag delays emergency care, and a
false alarm on routine knee pain trains staff to ignore the system.
"""
import pytest

from app.ai.emergency import screen_utterance
from app.models.enums import Department

pytestmark = pytest.mark.unit

ORTHO = Department.ORTHOPEDICS
GYN = Department.GYNECOLOGY


@pytest.mark.parametrize(
    "utterance,department,expected_flag",
    [
        ("Mujhe seene mein dard ho raha hai", ORTHO, "chest_pain"),
        ("saans nahi aa rahi", ORTHO, "breathlessness"),
        ("I fell down and my bone is sticking out of my leg", ORTHO,
         "open_or_deformed_fracture"),
        ("mera pair sunn ho gaya hai aur thanda lag raha hai", ORTHO, "limb_numb_cold"),
        ("my leg is numb and cold since the accident", ORTHO, "limb_numb_cold"),
        ("I cannot pass urine and my back is very painful", ORTHO, "cauda_equina"),
        ("haddi bahar nikal gayi hai", ORTHO, "open_or_deformed_fracture"),
        ("I am pregnant and there is bleeding since morning", GYN, "pregnancy_bleeding"),
        ("baby is not moving since yesterday", GYN, "reduced_fetal_movement"),
        ("bacche ki halchal kam ho gayi hai", GYN, "reduced_fetal_movement"),
        ("bleeding after menopause for two weeks", GYN, "postmenopausal_bleeding"),
        ("I feel like I want to kill myself", GYN, "suicidal_ideation"),
        ("she became unconscious for a minute", ORTHO, "loss_of_consciousness"),
    ],
)
def test_detects_red_flags(utterance, department, expected_flag):
    assert expected_flag in screen_utterance(utterance, department).flags


@pytest.mark.parametrize(
    "utterance,department",
    [
        ("My knee hurts when I climb stairs", ORTHO),
        ("मुझे बहुत तेज़ घुटने में दर्द है", ORTHO),
        ("I have back pain since three months, worse in the morning", ORTHO),
        ("Shoulder pain after lifting a heavy bag last week", ORTHO),
        ("I had a knee replacement surgery in 2019", ORTHO),
        ("My periods are irregular and painful for six months", GYN),
        ("White discharge for two weeks, no fever", GYN),
        ("I take metformin for sugar and have a mild cold", ORTHO),
    ],
)
def test_routine_complaints_do_not_trigger(utterance, department):
    """False alarms are their own harm: they teach staff to ignore alerts."""
    assert screen_utterance(utterance, department).flags == []


def test_department_specific_flags_are_scoped():
    """An obstetric flag must not fire in an orthopedic consultation."""
    result = screen_utterance("baby is not moving since yesterday", ORTHO)
    assert "reduced_fetal_movement" not in result.flags


def test_multiple_flags_are_all_reported():
    result = screen_utterance(
        "Mujhe seene mein dard ho raha hai aur saans nahi aa rahi", ORTHO
    )
    assert {"chest_pain", "breathlessness"} <= set(result.flags)
    assert result.is_emergency
