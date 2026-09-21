"""Refuse to save a department this site does not run.

A consultant was filed under Orthopedics at a gastroenterology clinic. The
screen showed Gastroenterology — its dropdown offered nothing else — but the
form underneath still held the value it started with, and the server took it.
The screen is fixed, and this is the reason it cannot quietly happen again:
every row written with a department is checked against ENABLED_DEPARTMENTS
before it reaches the database, whichever screen or script wrote it.

Only rows being inserted, or updated with a changed department, are checked.
A hospital that later narrows its list keeps its history readable and
editable; what it cannot do is file anything new under a department it no
longer runs.
"""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import Department


class DepartmentNotRun(ValueError):
    """A write named a department this site does not run."""


def _department_changes(session: Session):
    for instance in list(session.new) + list(session.dirty):
        if not hasattr(instance, "department"):
            continue
        value = getattr(instance, "department", None)
        if not isinstance(value, Department):
            continue
        if instance in session.dirty:
            history = inspect(instance).attrs.department.history
            if not history.has_changes():
                continue
        yield instance, value


def _check(session: Session, flush_context, instances) -> None:  # noqa: ARG001
    allowed = set(settings.enabled_departments)
    for instance, value in _department_changes(session):
        if value not in allowed:
            raise DepartmentNotRun(
                f"This site does not run {value.value}. Choose one of: "
                + ", ".join(d.value for d in settings.enabled_departments)
                + f" ({type(instance).__name__})."
            )


def install() -> None:
    """Register the check on every session. Safe to call more than once."""
    if not event.contains(Session, "before_flush", _check):
        event.listen(Session, "before_flush", _check)
