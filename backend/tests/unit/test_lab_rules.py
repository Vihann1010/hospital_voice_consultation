"""Laboratory rules: typed values, ranges, flags, cultures, verification."""
from types import SimpleNamespace

import pytest

from app.core.permissions import Permission, has_permission
from app.investigations import catalog
from app.investigations.reference_ranges import _clean, normalize_unit
from app.lab import defaults, rules
from app.models.enums import UserRole

pytestmark = pytest.mark.unit

HB = {"id": "hb", "name": "Haemoglobin", "result_type": "numeric", "unit": "g/dL",
      "ranges": defaults.starter_ranges("hemoglobin")}
K = {"id": "k", "name": "Potassium", "result_type": "numeric", "unit": "mEq/L",
     "ranges": [{"low": 3.5, "high": 5.1, "critical_low": 2.5, "critical_high": 6.5}]}


# ------------------------------------------------------------------ numbers
@pytest.mark.parametrize("typed, operator, number", [
    ("12.5", None, 12.5), ("1,50,000", None, 150000), ("150,000", None, 150000),
    ("1,500,000", None, 1500000), ("<0.5", "<", 0.5), ("> 1000", ">", 1000), ("-2.5", None, -2.5),
])
def test_numbers_that_are_unambiguous_are_read(typed, operator, number):
    assert rules.read_number(typed) == rules.Reading(operator, number)


@pytest.mark.parametrize("typed", ["12,5", "12,34", "abc", ".5", "12.5.1", "<-1", "1-0-1", "13 - 17", ""])
def test_anything_ambiguous_is_not_a_number(typed):
    assert rules.read_number(typed) is None


# ------------------------------------------------------------------- ranges
def test_the_patients_own_range_is_chosen():
    assert rules.select_range(HB["ranges"], sex="male", age=30)["low"] == 13.0
    assert rules.select_range(HB["ranges"], sex="female", age=30)["low"] == 12.0
    assert rules.select_range(HB["ranges"], sex="male", age=10)["low"] == 11.5


def test_sex_is_never_assumed():
    assert rules.select_range(HB["ranges"], sex=None, age=30) is None
    judged = rules.evaluate(HB, "9.0", sex=None, age=30)
    assert judged["flag"] is None
    assert "not compared" in judged["note"]


def test_range_problems_are_named():
    problems = rules.validate_ranges([
        {"sex": "male", "min_age": 0, "max_age": 60, "low": 10, "high": 5},
        {"sex": "male", "min_age": 50, "max_age": 120, "low": 1, "high": 5},
        {"sex": None, "low": None, "high": None},
    ])
    assert "Males aged 0-60: the lower limit is above the upper limit" in problems
    assert any("overlap" in problem for problem in problems)
    assert "Everyone: give a lower or an upper limit" in problems


# --------------------------------------------------------------------- flags
@pytest.mark.parametrize("typed, flag", [
    ("4.2", "normal"), ("3.1", "low"), ("5.6", "high"), ("2.4", "critical_low"), ("7.0", "critical_high"),
    ("2.5", "critical_low"), ("6.5", "critical_high"),
])
def test_numeric_flags(typed, flag):
    assert rules.evaluate(K, typed, sex="male", age=40)["flag"] == flag


def test_a_limit_is_flagged_only_when_it_settles_the_question():
    crp = {"name": "CRP", "result_type": "numeric", "ranges": [{"low": 0, "high": 5}]}
    assert rules.evaluate(crp, "<0.5", sex="female", age=30)["flag"] == "normal"
    assert rules.evaluate(crp, ">200", sex="female", age=30)["flag"] == "high"
    albumin = {"name": "Albumin", "result_type": "numeric", "ranges": [{"low": 3.5, "high": 5.2}]}
    assert rules.evaluate(albumin, "<2", sex="female", age=30)["flag"] == "low"
    judged = rules.evaluate(albumin, "<4", sex="female", age=30)
    assert judged["flag"] is None and "not compared" in judged["note"]


def test_no_range_means_no_flag():
    judged = rules.evaluate({"name": "Neutrophils", "result_type": "numeric", "ranges": []}, "92",
                            sex="male", age=40)
    assert judged == {"flag": None, "reference_text": None, "note": "No reference range set; not compared",
                      "error": None}


def test_a_value_that_is_not_a_number_is_refused():
    assert "is not a number" in rules.evaluate(K, "4,2", sex="male", age=40)["error"]


def test_choices():
    hbsag = {"name": "HBsAg", "result_type": "choice", "choices": ["Non-reactive", "Reactive"],
             "normal_values": ["Non-reactive"]}
    assert rules.evaluate(hbsag, "reactive", sex=None, age=30)["flag"] == "abnormal"
    assert rules.evaluate(hbsag, "Non-reactive", sex=None, age=30)["flag"] == "normal"
    assert "choose one of" in rules.evaluate(hbsag, "weak positive", sex=None, age=30)["error"]
    upt = {"name": "UPT", "result_type": "choice", "choices": ["Negative", "Positive"], "normal_values": []}
    assert rules.evaluate(upt, "Positive", sex="female", age=25)["flag"] is None


def test_the_printed_range_follows_the_patient():
    rows, errors = rules.evaluate_all([HB], {"hb": "11.0"}, {}, sex="female", age=30)
    assert errors == []
    assert rows[0]["flag"] == "low" and rows[0]["reference_text"] == "12 - 15"


# ------------------------------------------------------------------- culture
def test_culture_needs_an_organism_and_a_panel():
    assert rules.check_culture({"specimen": "Urine", "growth": "growth", "isolates": [
        {"organism": "Escherichia coli", "antibiotics": [{"name": "Nitrofurantoin", "result": "s"},
                                                       {"name": "Ciprofloxacin", "result": "R"}]}]}) == []
    problems = rules.check_culture({"specimen": "Urine", "growth": "growth", "isolates": [
        {"organism": "", "antibiotics": [{"name": "Amikacin", "result": "X"}, {"name": "amikacin", "result": "S"}]}]})
    assert "Organism 1: name the organism" in problems
    assert "Organism 1: mark Amikacin S, I or R" in problems
    assert "Organism 1: amikacin is listed twice" in problems


def test_no_growth_cannot_carry_organisms():
    assert rules.check_culture({"specimen": "Urine", "growth": "no_growth"}) == []
    assert rules.check_culture({"specimen": "Urine", "growth": "no_growth",
                                "isolates": [{"organism": "E. coli"}]}) == [
        "Remove the organisms: the culture is recorded as no growth"]
    assert rules.check_culture({}) == ["Record the specimen cultured", "Record whether there was growth"]


# -------------------------------------------------------------- verification
def test_every_printed_line_needs_a_value():
    heading = {"id": "h", "name": "Differential count", "result_type": "heading"}
    neut = {"id": "n", "name": "Neutrophils", "result_type": "numeric", "ranges": []}
    rows, errors = rules.evaluate_all([heading, HB, neut], {"hb": "13.5"}, {}, sex="male", age=40)
    assert rules.check_for_verify(is_culture=False, rows=rows, culture=None, errors=errors) == [
        "Enter Neutrophils, or untick it from printing"]
    rows, errors = rules.evaluate_all([heading, HB, neut], {"hb": "13.5"}, {"n": False}, sex="male", age=40)
    assert rules.check_for_verify(is_culture=False, rows=rows, culture=None, errors=errors) == []


def test_request_status():
    assert rules.request_status(["registered", "cancelled"]) == "registered"
    assert rules.request_status(["collected", "entered"]) == "in_progress"
    assert rules.request_status(["verified", "entered"]) == "partly_verified"
    assert rules.request_status(["verified", "cancelled"]) == "verified"
    assert rules.request_status(["cancelled"]) == "cancelled"


# --------------------------------------------------------------- printouts
def _line(name, value=None, unit=None, text=None, key=None, raw=None):
    return SimpleNamespace(printed_name=name, analyte_key=key, value_numeric=value, value_text=text,
                           operator=None, unit=unit, raw_line=raw or f"{name} {value or text} {unit or ''}")


def test_printout_suggests_only_what_it_can_stand_behind():
    parameters = [dict(HB), dict(K, analyte_key="potassium"),
                  {"id": "plt", "name": "Platelet count", "result_type": "numeric", "unit": "lakh/cumm",
                   "analyte_key": "platelet_count"}]
    parameters[0]["analyte_key"] = "hemoglobin"
    parsed = [
        _line("Haemoglobin", 12.4, "g/dl", key="hemoglobin"),
        _line("Potassium", 4.1, "mEq/L", key="potassium"),
        _line("K+", 4.3, "mEq/L", key="potassium"),
        _line("Platelets", 145000, "/cumm", key="platelet_count"),
        _line("Regd No", 24294),
    ]
    out = rules.match_printout(parameters, parsed, normalize_unit=normalize_unit, clean_name=_clean)
    assert out["suggestions"] == [{"parameter_id": "hb", "name": "Haemoglobin", "value": "12.4",
                                   "raw_line": "Haemoglobin 12.4 g/dl"}]
    assert out["conflicts"] == ["Potassium appears 2 times on the printout; enter it by hand"]
    assert len(out["unit_mismatches"]) == 1 and "lakh/cumm" in out["unit_mismatches"][0]
    assert out["unmatched_count"] == 1


# ------------------------------------------------------------------ defaults
def test_every_starter_test_is_valid():
    codes = set()
    for code, name, group, _specimen, catalog_code, _service, parameters, culture, hours in defaults.TESTS:
        assert code not in codes
        codes.add(code)
        assert group in defaults.GROUPS
        assert hours > 0
        if catalog_code:
            assert catalog.get(catalog_code) is not None, catalog_code
        if not culture:
            assert any(entry["result_type"] != "heading" for entry in parameters), code
        for entry in parameters:
            assert rules.validate_ranges(entry.get("ranges") or []) == [], (code, entry["name"])
            if entry["result_type"] == "choice":
                assert set(entry.get("normal_values") or []) <= set(entry["choices"])


# --------------------------------------------------------------- permissions
def test_only_a_doctor_verifies_and_the_bench_enters():
    assert has_permission(UserRole.DOCTOR, Permission.LAB_RESULT_VERIFY)
    assert not has_permission(UserRole.LAB, Permission.LAB_RESULT_VERIFY)
    assert not has_permission(UserRole.LAB, Permission.LAB_MASTER_MANAGE)
    assert not has_permission(UserRole.LAB, Permission.INVOICE_CREATE)
    assert has_permission(UserRole.LAB, Permission.LAB_RESULT_ENTER)
    for role in (UserRole.RECEPTION, UserRole.SUPERVISOR, UserRole.NURSE, UserRole.LAB):
        assert has_permission(role, Permission.LAB_REGISTER)
    assert not has_permission(UserRole.MANAGER, Permission.LAB_REGISTER)
    assert not has_permission(UserRole.NURSE, Permission.LAB_RESULT_ENTER)


# ------------------------------------------------------------------ printing
def test_report_prints_verified_results_and_lists_pending_ones():
    from datetime import datetime, timezone

    from app.lab.report_pdf import render_lab_report

    now = datetime(2026, 9, 13, 9, 30, tzinfo=timezone.utc)
    rows, _ = rules.evaluate_all([HB, K], {"hb": "11.0", "k": "7.0"}, {}, sex="female", age=30)
    verified = SimpleNamespace(
        position=0, status="verified", group_name="Biochemistry", name="Profile", is_culture=False,
        results=rows, culture=None, remarks="Haemolysed sample excluded", critical_note="Dr Rao told 09:40",
        version=2, amendments=[{"reason": "Wrong unit typed"}], verified_by_name="Dr Mehta",
        verifier_qualification="MD Pathology", verifier_registration="UPMC 1234", verified_at=now)
    culture = SimpleNamespace(
        position=1, status="verified", group_name="Microbiology", name="Urine Culture", is_culture=True,
        results=[], culture={"specimen": "Urine", "growth": "growth", "isolates": [
            {"organism": "Escherichia coli", "colony_count": ">10^5 CFU/mL",
             "antibiotics": [{"name": "Nitrofurantoin", "result": "S"}, {"name": "Ciprofloxacin", "result": "R"}]}]},
        remarks=None, critical_note=None, version=1, amendments=[], verified_by_name="Dr Mehta",
        verifier_qualification="MD Pathology", verifier_registration="UPMC 1234", verified_at=now)
    pending = SimpleNamespace(position=2, status="entered", group_name="Haematology", name="ESR")
    request = SimpleNamespace(lab_number="LAB26-00001", created_at=now, sample_collected_at=now,
                              referred_by="Dr Rao", priority="urgent")
    patient = SimpleNamespace(name="Asha Devi", age=30, gender=SimpleNamespace(value="female"), uhid="SAT26AAAAAC")
    pdf = render_lab_report(request=request, items=[verified, culture, pending], patient=patient)
    assert pdf.startswith(b"%PDF")
