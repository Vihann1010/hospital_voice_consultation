"""Deterministic lab report parsing and reference-range flagging."""
import pytest

from app.investigations.parsing import analyze_text
from app.investigations.reference_ranges import range_for, resolve_analyte
from app.models.enums import AbnormalFlag, Gender

pytestmark = pytest.mark.unit

REPORT = """
COMPLETE BLOOD COUNT
Hemoglobin                9.2      g/dL        12.0 - 15.0
Total Leukocyte Count     12800    cells/cumm  4000 - 11000
Platelet Count            2.4      lakh/cumm   1.5 - 4.1
ESR                       48       mm/hr       0 - 20
BIOCHEMISTRY
Fasting Blood Sugar  :    142      mg/dL       70 - 100
HbA1c                     7.8      %           4.0 - 5.6
S. Creatinine             0.9      mg/dL       0.6 - 1.1
S. Calcium                8.9      mg/dL
Vitamin D (25-OH)         14.3     ng/mL       30 - 100
Total Cholesterol         245      mg/dL       Upto 200
URINE ROUTINE
Urine Protein             Absent
Pus Cells                 12       /hpf        0 - 5
Blood                     Present
IMPRESSION: Microcytic hypochromic anaemia with raised ESR.
"""


@pytest.fixture(scope="module")
def parsed():
    report = analyze_text(REPORT, sex=Gender.FEMALE, age=52)
    return {result.analyte_key: result for result in report.results if result.analyte_key}


@pytest.mark.parametrize(
    "analyte,expected",
    [
        ("hemoglobin", AbnormalFlag.LOW),
        ("total_leukocyte_count", AbnormalFlag.HIGH),
        ("platelet_count", AbnormalFlag.NORMAL),
        ("esr", AbnormalFlag.HIGH),
        ("fasting_glucose", AbnormalFlag.HIGH),
        ("hba1c", AbnormalFlag.HIGH),
        ("creatinine", AbnormalFlag.NORMAL),
        ("vitamin_d", AbnormalFlag.LOW),
        ("total_cholesterol", AbnormalFlag.HIGH),
        ("urine_protein", AbnormalFlag.NORMAL),
        ("urine_pus_cells", AbnormalFlag.HIGH),
        ("urine_blood", AbnormalFlag.ABNORMAL),
    ],
)
def test_values_are_flagged_correctly(parsed, analyte, expected):
    assert parsed[analyte].flag is expected


def test_falls_back_to_builtin_range_when_report_prints_none(parsed):
    """Calcium is printed without a range, so the built-in one must apply."""
    calcium = parsed["calcium"]
    assert calcium.reference_source == "builtin"
    assert calcium.flag is AbnormalFlag.NORMAL


def test_open_ended_range_is_understood(parsed):
    assert parsed["total_cholesterol"].reference_high == 200.0


def test_sections_are_attributed():
    report = analyze_text(REPORT, sex=Gender.FEMALE, age=52)
    sections = {r.display_name: r.section for r in report.results}
    assert sections["Hemoglobin"] == "COMPLETE BLOOD COUNT"
    assert sections["Pus Cells"] == "URINE ROUTINE"


def test_narrative_lines_are_captured():
    report = analyze_text(REPORT, sex=Gender.FEMALE, age=52)
    assert any("IMPRESSION" in line for line in report.narrative_lines)


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("Haemoglobin", "hemoglobin"), ("HB", "hemoglobin"),
        ("S. Creatinine", "creatinine"), ("B. Urea", "urea"),
        ("Plasma Glucose Fasting", "fasting_glucose"),
        ("CA-125", "ca_125"), ("SGPT (ALT)", "sgpt"),
        ("Vitamin D3", "vitamin_d"), ("Random garbage text", None),
    ],
)
def test_analyte_name_resolution(printed, expected):
    assert resolve_analyte(printed) == expected


def test_reference_range_varies_by_sex_and_age():
    male = range_for("hemoglobin", sex=Gender.MALE, age=45)
    female = range_for("hemoglobin", sex=Gender.FEMALE, age=30)
    child = range_for("hemoglobin", sex=Gender.MALE, age=8)
    assert (male.low, male.high) == (13.0, 17.0)
    assert (female.low, female.high) == (12.0, 15.0)
    assert (child.low, child.high) == (11.5, 15.5)


def test_unconvertible_units_are_not_flagged():
    """A wrong flag on a lab value is worse than no flag."""
    report = analyze_text("Hemoglobin  92  mmol/L", sex=Gender.FEMALE, age=30)
    result = next(r for r in report.results if r.analyte_key == "hemoglobin")
    assert result.flag is AbnormalFlag.UNKNOWN
    assert "Not compared" in (result.note or "")
