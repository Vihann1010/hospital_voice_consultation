"""Gastroenterology clinical content, and the sign-off gate in front of it.

The gate is the point of most of this file. Drafted prescribing content was
written by whoever added the speciality, not by a consultant who practises it,
and "needs review" in a comment is not a control. Until a gastroenterologist
signs it off, a drafted regimen must not be reachable from a prescribing
screen — not by search, not through a template, not by typing its code.
"""
import pytest

from app.core.config import Settings, settings
from app.investigations import catalog
from app.models.enums import Department, InvestigationCategory
from app.prescriptions import formulary

pytestmark = pytest.mark.unit

GASTRO = Department.GASTROENTEROLOGY


@pytest.fixture
def approved_gastro(monkeypatch):
    """Sign the gastro content off, as a consultant eventually will."""
    monkeypatch.setattr(
        settings, "APPROVED_FORMULARY", "orthopedics,gynecology,gastroenterology"
    )


# ------------------------------------------------------------- the gate


def test_drafted_content_is_withheld_until_signed_off():
    assert not any(m.provisional for m in formulary.search(department=GASTRO, limit=500))
    assert formulary.search_templates(department=GASTRO) == []


def test_a_drafted_medicine_cannot_be_fetched_by_code():
    """Search is not the only way in; the code is the other one."""
    assert formulary.get("RIFAXIMIN") is None
    assert formulary.get("CLARITHROMYCIN") is None


def test_a_drafted_regimen_is_not_reachable_through_a_template():
    """The path the copilot takes: template -> medicine codes -> formulary.get."""
    for template in formulary.MEDICINE_TEMPLATES:
        if template.department is not GASTRO:
            continue
        assert all(formulary.get(code) is None or not formulary.get(code).provisional
                   for code in template.medicine_codes)


def test_an_issued_prescription_stays_readable():
    """Withholding a drug from prescribing must not hide what a patient took."""
    drug = formulary.get_including_unapproved("RIFAXIMIN")
    assert drug is not None and drug.name == "Rifaximin"


def test_signing_off_releases_the_content(approved_gastro):
    codes = {m.code for m in formulary.search(department=GASTRO, limit=500)}
    assert {"UDCA", "LACTULOSE", "MESALAMINE", "RIFAXIMIN"} <= codes
    diseases = {t.disease_name for t in formulary.search_templates(department=GASTRO)}
    assert any("H. pylori" in name for name in diseases)
    assert formulary.get("RIFAXIMIN") is not None


def test_the_existing_departments_are_unaffected():
    """Orthopedics and gynecology were reviewed before release and stay open."""
    assert formulary.search(department=Department.ORTHOPEDICS)
    assert formulary.search_templates(department=Department.GYNECOLOGY)
    assert formulary.get("PARA") is not None


def test_pending_signoff_is_reported_for_the_startup_log():
    assert formulary.unapproved_departments() == [GASTRO]


def test_approval_setting_rejects_a_name_that_is_not_a_department():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(APPROVED_FORMULARY="orthopedics,gastro")


# --------------------------------------------------- the drafted content


def test_every_gastro_medicine_is_marked_provisional():
    """Nothing drafted here may ship as though it had been reviewed."""
    drafted = [m for m in formulary.FORMULARY if GASTRO in m.departments]
    assert drafted, "the gastro formulary is missing"
    assert all(m.provisional for m in drafted)


def test_every_gastro_template_is_marked_provisional_and_names_its_caution():
    drafted = [t for t in formulary.MEDICINE_TEMPLATES if t.department is GASTRO]
    assert drafted
    for template in drafted:
        assert template.provisional
        assert "review" in template.note.lower()


def test_templates_only_name_medicines_that_exist():
    """A template pointing at a missing code silently prescribes less than it says."""
    for template in formulary.MEDICINE_TEMPLATES:
        for code in template.medicine_codes:
            assert code in formulary.FORMULARY_BY_CODE, (
                f"{template.disease_name} names unknown medicine {code}"
            )


def test_h_pylori_first_line_is_a_full_fourteen_day_triple():
    template = next(
        t for t in formulary.MEDICINE_TEMPLATES
        if t.department is GASTRO and "first line" in t.disease_name
    )
    drugs = [formulary.get_including_unapproved(c) for c in template.medicine_codes]
    classes = {d.category for d in drugs}
    assert "Proton pump inhibitor" in classes
    assert len([d for d in drugs if "antibiotic" in d.category.lower()]) == 2
    assert all(d.default_duration == "14 days" for d in drugs)


# ------------------------------------------------------- investigations


def test_the_clinic_can_order_what_a_gi_clinic_orders():
    codes = {item.code for item in catalog.search(department=GASTRO, limit=500)}
    for expected in ("GI_OGD", "GI_COLONOSCOPY", "GI_HPYLORI_UBT", "GI_ELASTOGRAPHY",
                     "GI_CALPROTECTIN", "GI_STOOL_RE", "LFT", "USG_ABDO"):
        assert expected in codes, f"{expected} is not orderable"


def test_gi_investigations_do_not_appear_in_other_departments():
    ortho = {item.code for item in catalog.search(department=Department.ORTHOPEDICS, limit=500)}
    assert "GI_OGD" not in ortho
    assert "GI_CALPROTECTIN" not in ortho


def test_scope_procedures_carry_their_preparation():
    """A colonoscopy with no bowel prep on the slip is a wasted appointment."""
    for code in ("GI_OGD", "GI_COLONOSCOPY"):
        item = catalog.get(code)
        assert item.category is InvestigationCategory.ENDOSCOPY
        assert item.preparation and len(item.preparation) > 20
    assert "consent" in catalog.get("GI_OGD").note.lower()


def test_breath_test_warns_about_the_ppi_washout():
    """On a PPI, the urea breath test reads negative when it is not."""
    assert "PPI" in catalog.get("GI_HPYLORI_UBT").preparation


def test_gi_panels_expand_to_real_codes():
    for panel_code in ("PANEL_DYSPEPSIA", "PANEL_LIVER", "PANEL_CHRONIC_DIARRHOEA",
                       "PANEL_SCOPE_PREOP"):
        expanded = catalog.expand_codes([panel_code])
        assert expanded, f"{panel_code} expands to nothing"


def test_pancreatic_enzymes_have_a_critical_high():
    """A lipase three times over is read the hour it arrives, not the next day."""
    from app.investigations.reference_ranges import REFERENCE_RANGES

    for analyte in ("amylase", "lipase"):
        assert REFERENCE_RANGES[analyte][0].critical_high is not None


# ------------------------------------------------------- safety checking


@pytest.mark.parametrize(
    "first,second,expected",
    [
        # The one that lands after the patient has gone home: a fourteen-day
        # course prescribed to somebody already on a statin.
        ("CLARITHROMYCIN", "ATORVA", "serious"),
        ("CLARITHROMYCIN", "DOMPERIDONE_10", "serious"),
        ("SUCRALFATE", "THYRONORM", "caution"),
        # Not every pair is an interaction; a table that alerts on everything
        # trains staff to click past it.
        ("PAN_40_BD", "AMOX_500", None),
        ("LACTULOSE", "ISABGOL", None),
    ],
)
def test_interaction_alerts_for_the_new_regimens(first, second, expected):
    from app.prescriptions.safety import check_interactions

    entries = [
        {"name": formulary.get_including_unapproved(code).name, "formulary_code": code}
        for code in (first, second)
    ]
    alerts = check_interactions(entries)
    if expected is None:
        assert not alerts
    else:
        assert any(a.severity == expected for a in alerts)


def test_interaction_checking_sees_through_the_signoff_gate():
    """A safety check that goes quiet while content awaits review is worse than none."""
    from app.prescriptions.safety import check_interactions

    # CLARITHROMYCIN is provisional and withheld from prescribing right now.
    assert formulary.get("CLARITHROMYCIN") is None
    alerts = check_interactions([
        {"name": "Clarithromycin", "formulary_code": "CLARITHROMYCIN"},
        {"name": "Atorvastatin", "formulary_code": "ATORVA"},
    ])
    assert any(a.severity == "serious" for a in alerts)


def test_clopidogrel_is_steered_to_pantoprazole():
    from app.prescriptions.safety import check_interactions

    alerts = check_interactions([
        {"name": "Omez", "formulary_code": "OMEZ"},
        {"name": "Clopidogrel"},
    ])
    assert alerts and "pantoprazole" in alerts[0].suggested_action.lower()
