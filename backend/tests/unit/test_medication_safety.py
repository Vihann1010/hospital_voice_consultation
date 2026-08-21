"""Prescribing safety rules: duplicates, allergies, interactions, pregnancy."""
import pytest

from app.prescriptions.safety import blocking_alerts, run_all

pytestmark = pytest.mark.unit


def med(name, code=None, frequency="BD"):
    return {"name": name, "formulary_code": code, "frequency_text": frequency}


def kinds(alerts):
    return {alert.kind for alert in alerts}


def test_allergy_conflict_is_serious():
    alerts = run_all([med("Augmentin 625", "AUGMENTIN")], allergies=["Penicillin"])
    allergy = [a for a in alerts if a.kind == "allergy"]
    assert allergy and allergy[0].severity == "serious"


def test_class_level_allergy_is_caught():
    """'NSAIDs' as an allergy must catch aceclofenac, not just exact names."""
    alerts = run_all([med("Zerodol", "ZERODOL")], allergies=["NSAIDs"])
    assert "allergy" in kinds(alerts)


@pytest.mark.parametrize(
    "first,second",
    [
        (("Dolo", "DOLO"), ("Crocin", "CROCIN")),               # same ingredient
        (("Metformin", "METFORMIN"), ("Glycomet", "GLYCOMET")), # brand + generic
    ],
)
def test_duplicate_ingredients_detected(first, second):
    alerts = run_all([med(*first), med(*second)])
    assert "duplicate" in kinds(alerts)


def test_same_class_stacking_detected():
    alerts = run_all([med("Zerodol", "ZERODOL"), med("Naprosyn", "NAPROSYN")])
    assert "duplicate" in kinds(alerts)


@pytest.mark.parametrize(
    "first,second",
    [
        (("Thyronorm", "THYRONORM"), ("Shelcal 500", "SHELCAL")),
        (("Cifran", "CIFRAN"), ("Calcimax", "CALCIMAX")),
        (("Prednisolone", "PREDNISOLONE"), ("Zerodol", "ZERODOL")),
    ],
)
def test_interactions_detected(first, second):
    alerts = run_all([med(*first), med(*second)])
    assert "interaction" in kinds(alerts)


def test_pregnancy_caution_only_when_relevant():
    with_pregnancy = run_all([med("Doxycycline", "DOXY")], pregnancy_possible=True)
    without = run_all([med("Doxycycline", "DOXY")], pregnancy_possible=False)
    assert "pregnancy" in kinds(with_pregnancy)
    assert "pregnancy" not in kinds(without)


def test_clean_prescription_produces_no_warnings():
    alerts = run_all([med("Paracetamol", "PARA"), med("Pantoprazole", "PAN")])
    assert [a for a in alerts if a.severity in ("serious", "caution")] == []


def test_missing_frequency_is_flagged():
    alerts = run_all([{"name": "Paracetamol", "formulary_code": "PARA"}])
    assert any(a.kind == "formulary" and a.severity == "caution" for a in alerts)


def test_blocking_alerts_are_the_serious_ones():
    alerts = run_all(
        [med("Augmentin 625", "AUGMENTIN"), med("Dolo", "DOLO"), med("Crocin", "CROCIN")],
        allergies=["Penicillin"],
    )
    blocking = blocking_alerts(alerts)
    assert len(blocking) >= 2
    assert all(alert.severity == "serious" for alert in blocking)
