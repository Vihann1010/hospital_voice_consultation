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
GASTRO = Department.GASTROENTEROLOGY


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
        ("I vomited blood this morning", GASTRO, "gi_bleeding"),
        ("ulti mein khoon aaya", GASTRO, "gi_bleeding"),
        ("my stool is black and tarry since two days", GASTRO, "gi_bleeding"),
        ("black stool since yesterday", GASTRO, "gi_bleeding"),
        ("melaena for three days", GASTRO, "gi_bleeding"),
        ("there is blood in my motion", GASTRO, "gi_bleeding"),
        ("pet phool gaya hai aur gas nahi nikal rahi", GASTRO, "bowel_obstruction"),
        ("severe stomach pain going to the back", GASTRO, "severe_epigastric_pain"),
        ("my eyes have turned yellow and urine is very dark", GASTRO, "jaundice"),
        ("aankhein peeli ho gayi hain", GASTRO, "jaundice"),
        ("food gets stuck when I swallow", GASTRO, "dysphagia"),
        ("मुझे सीने में दर्द हो रहा है", GASTRO, "chest_pain"),
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
        ("I get acidity after eating spicy food", GASTRO),
        ("loose motions for two days after a wedding meal", GASTRO),
        ("khana khane ke baad pet bhari lagta hai", GASTRO),
        ("constipation since a month, no bleeding", GASTRO),
        # "black" next to "motion" is not enough on its own.
        ("my motion is normal and black tea in the morning", GASTRO),
    ],
)
def test_routine_complaints_do_not_trigger(utterance, department):
    """False alarms are their own harm: they teach staff to ignore alerts."""
    assert screen_utterance(utterance, department).flags == []


def test_department_specific_flags_are_scoped():
    """An obstetric flag must not fire in an orthopedic consultation."""
    result = screen_utterance("baby is not moving since yesterday", ORTHO)
    assert "reduced_fetal_movement" not in result.flags


def test_gastro_flags_do_not_fire_in_other_departments():
    """A GI flag belongs to the GI consultation, like every other scoped flag."""
    assert "gi_bleeding" not in screen_utterance("blood in my motion", ORTHO).flags


def test_unconfigured_department_raises_rather_than_passing_everything():
    """The failure this module must never have: screening against nothing.

    A department with no red-flag block used to return an empty list, which is
    indistinguishable from "no emergency found". It now raises.
    """
    import app.ai.emergency as emergency
    from app.departments import DepartmentNotConfigured

    original = emergency._COMPILED_DEPT
    emergency._COMPILED_DEPT = {
        d: v for d, v in original.items() if d is not Department.GASTROENTEROLOGY
    }
    try:
        with pytest.raises(DepartmentNotConfigured):
            screen_utterance("I vomited blood this morning", GASTRO)
    finally:
        emergency._COMPILED_DEPT = original


def test_multiple_flags_are_all_reported():
    result = screen_utterance(
        "Mujhe seene mein dard ho raha hai aur saans nahi aa rahi", ORTHO
    )
    assert {"chest_pain", "breathlessness"} <= set(result.flags)
    assert result.is_emergency


DENTAL = Department.DENTISTRY


@pytest.mark.parametrize(
    "utterance, expected_flag",
    [
        ("my face swelling is increasing since morning", "spreading_facial_swelling"),
        ("gaal ki soojan badh rahi hai", "spreading_facial_swelling"),
        ("swelling in my jaw and I cannot swallow properly", "swallowing_or_breathing_with_infection"),
        ("I cannot open my mouth and I have fever", "trismus"),
        ("muh nahi khul raha", "trismus"),
        ("tooth was extracted yesterday and bleeding is not stopping", "post_extraction_bleeding"),
        ("daant nikalwaya tha khoon band nahi ho raha", "post_extraction_bleeding"),
        ("my son fell and his tooth got knocked out", "knocked_out_tooth"),
        ("my jaw is broken after an accident", "jaw_injury"),
    ],
)
def test_dental_red_flags(utterance, expected_flag):
    assert expected_flag in screen_utterance(utterance, DENTAL).flags


@pytest.mark.parametrize(
    "utterance",
    [
        "cold water gives sensitivity in my teeth",
        "my gums bleed when brushing",
        "I have a cavity in the back tooth and it hurts when I eat sweets",
        "swelling on gum near wisdom tooth",
        "I want my teeth cleaned",
    ],
)
def test_routine_dental_complaints_do_not_trigger(utterance):
    assert screen_utterance(utterance, DENTAL).flags == []


def test_dental_flags_do_not_fire_in_gastroenterology():
    assert "trismus" not in screen_utterance("muh nahi khul raha", GASTRO).flags
