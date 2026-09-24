"""The Hindi sections are Hindi, in Devanagari.

Asked for Hindi after a Hinglish intake, a model mirrors the patient and
returns "daant mein tez dard". The patient's printed copy then carries
Roman-script Hindi, and the section is not what it says it is. The schema
refuses it, which is what makes the stage ask the model again.
"""
import pytest
from pydantic import ValidationError

from app.ai.pipeline.schemas import ClinicalSummary, PatientEducation

pytestmark = pytest.mark.unit


def test_devanagari_is_accepted():
    summary = ClinicalSummary.model_validate(
        {"history_points_hi": ["3 दिन पहले दांत में तेज़ दर्द शुरू हुआ।",
                               "चबाने पर दर्द बढ़ता है।"]}
    )
    assert len(summary.history_points_hi) == 2


def test_roman_transliteration_is_refused():
    with pytest.raises(ValidationError) as exc:
        ClinicalSummary.model_validate(
            {"history_points_hi": ["3 din pehle daant mein tez dard shuru hua tha."]}
        )
    assert "Devanagari" in str(exc.value)


def test_a_drug_or_test_name_in_latin_letters_is_fine():
    """PAN 40 has no Devanagari spelling anybody would recognise."""
    summary = ClinicalSummary.model_validate(
        {"history_points_hi": ["मरीज़ PAN 40 ले रहे हैं।", "OGD पहले हो चुकी है।"]}
    )
    assert len(summary.history_points_hi) == 2


def test_english_advice_is_untouched():
    education = PatientEducation.model_validate(
        {"general_self_care": ["Drink warm water"],
         "general_self_care_hi": ["गर्म पानी पिएं।"],
         "warning_signs_return_immediately_hi": ["बुखार आए तो तुरंत आएं।"]}
    )
    assert education.general_self_care == ["Drink warm water"]


def test_patient_education_refuses_hinglish():
    with pytest.raises(ValidationError):
        PatientEducation.model_validate({"general_self_care_hi": ["garm paani piyen"]})
