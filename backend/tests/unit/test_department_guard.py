"""A department the site does not run cannot be saved.

A consultant was filed under Orthopedics at a gastroenterology clinic: the
screen showed the only department on offer, the form still held the one it
started with, and the server accepted it. The screen is fixed; this is the
check that makes the same mistake from any other screen or script refuse
loudly instead of saving quietly.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.db import department_guard
from app.models.consultant import Consultant
from app.models.enums import Department

pytestmark = pytest.mark.unit


@pytest.fixture
def gastro_only(monkeypatch):
    monkeypatch.setattr(settings, "ENABLED_DEPARTMENTS", "gastroenterology")


def _flush(instance):
    """Run the guard exactly as a real flush would, without a database."""
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        session.add(instance)
        department_guard._check(session, None, None)


def test_a_department_the_site_does_not_run_is_refused(gastro_only):
    with pytest.raises(department_guard.DepartmentNotRun) as exc:
        _flush(Consultant(full_name="Dr. Piyush Mishra", department=Department.ORTHOPEDICS))
    assert "orthopedics" in str(exc.value)
    assert "gastroenterology" in str(exc.value)


def test_the_site_department_is_accepted(gastro_only):
    _flush(Consultant(full_name="Dr. Piyush Mishra", department=Department.GASTROENTEROLOGY))


def test_a_hospital_running_everything_is_unaffected():
    """Satya sets nothing, so every department stays writable there."""
    assert Settings(ENABLED_DEPARTMENTS="").enabled_departments == list(Department)
    _flush(Consultant(full_name="Dr. Anyone", department=Department.GYNECOLOGY))


def test_the_default_department_falls_back_to_one_the_site_runs():
    """DEFAULT_DEPARTMENT defaults to orthopedics; a clinic that forgets to set
    it must not have its screens start on a department it does not have."""
    config = Settings(ENABLED_DEPARTMENTS="gastroenterology", DEFAULT_DEPARTMENT="orthopedics")
    assert config.default_department is Department.GASTROENTEROLOGY


def test_the_guard_installs_once():
    department_guard.install()
    department_guard.install()
    from sqlalchemy import event

    assert event.contains(Session, "before_flush", department_guard._check)


def test_the_catalogue_offers_only_what_the_site_runs(gastro_only):
    from app.investigations import catalog

    codes = {item.code for item in catalog.search(limit=1000)}
    assert "GI_OGD" in codes
    assert "GYN_PAP" not in codes          # not even to a user with no department
    assert "ORTHO_NCV" not in codes
    assert "CBC" in codes                  # general tests stay


def test_the_formulary_offers_only_what_the_site_runs(gastro_only):
    from app.prescriptions import formulary

    names = {m.code for m in formulary.search(limit=1000)}
    assert "PARA" in names                 # general
    assert "ZERODOL" not in names          # orthopaedic
    assert formulary.search_templates() == [] or all(
        t.department is Department.GASTROENTEROLOGY for t in formulary.search_templates()
    )
