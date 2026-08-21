"""Prescription dictation parsing."""
import pytest

from app.prescriptions.dictation import parse_dictation, split_dictation

pytestmark = pytest.mark.unit


def test_the_reference_dictation():
    """The exact phrasing the module was specified against."""
    medicines = parse_dictation(
        "Tablet Paracetamol 650 mg SOS. "
        "Tablet Pantoprazole 40 mg before breakfast. "
        "Tablet Calcium once daily."
    )
    assert len(medicines) == 3
    assert medicines[0].name == "Paracetamol"
    assert medicines[0].strength == "650 mg"
    assert medicines[0].frequency_code == "SOS"
    assert medicines[1].name == "Pantoprazole"
    assert medicines[1].timing == "Before breakfast"
    assert medicines[2].frequency_code == "OD"


@pytest.mark.parametrize(
    "spoken,name,frequency,timing,duration",
    [
        ("Tab Zerodol SP twice daily after food for 5 days",
         "Zerodol SP", "BD", "After food", "5 days"),
        ("Capsule Myoril 4 mg BD for one week", "Myoril", "BD", None, "1 week"),
        ("Tablet Thyronorm 50 mcg once daily empty stomach continue",
         "Thyronorm", "OD", "On an empty stomach", "Continue"),
        ("Injection Tranexamic acid 500 mg three times a day for 5 days",
         "Tranexamic Acid", "TDS", None, "5 days"),
        ("Tablet Augmentin 625 mg twice daily x 5 days after food",
         "Augmentin 625", "BD", "After food", "5 days"),
        ("Uprise D3 60000 IU once weekly for 8 weeks",
         "Uprise D3", "WEEKLY", None, "8 weeks"),
        ("Tablet Etoshine 90 mg at bedtime for 5 days",
         "Etoshine", "HS", "At bedtime", "5 days"),
        ("Tablet Fluconazole 150 mg stat", "Fluconazole", "STAT", None, None),
        ("Tablet Pregabalin 75 mg at night for one month",
         "Pregabalin", "HS", "At bedtime", "1 month"),
    ],
)
def test_dictation_variants(spoken, name, frequency, timing, duration):
    medicine = parse_dictation(spoken)[0]
    assert medicine.name == name
    assert medicine.frequency_code == frequency
    if timing is not None:
        assert medicine.timing == timing
    if duration is not None:
        assert medicine.duration == duration


def test_bedtime_frequency_implies_bedtime_timing():
    """HS carries its own timing; a formulary default must not override it."""
    medicine = parse_dictation("Tablet Etoshine 90 mg at bedtime")[0]
    assert medicine.timing == "At bedtime"


def test_brand_substitution_is_surfaced():
    """Dictating a generic must not silently become a brand."""
    medicine = parse_dictation("Tablet Calcium once daily")[0]
    assert medicine.substituted is True
    assert medicine.confidence < 0.8
    assert any("confirm" in warning.lower() for warning in medicine.warnings)


def test_unknown_drug_is_flagged_not_guessed():
    medicine = parse_dictation("Tablet Zephyrolol 10 mg BD")[0]
    assert medicine.unmatched is True
    assert medicine.warnings


def test_segmentation_handles_run_on_speech():
    segments = split_dictation(
        "Tablet Paracetamol 650 mg SOS and Tablet Pantoprazole 40 mg once daily"
    )
    assert len(segments) == 2
