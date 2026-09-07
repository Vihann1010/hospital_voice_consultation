"""Department scoping.

A consultant sees their own department's patients and nobody else's. This is a
confidentiality boundary, so it is enforced in the API rather than by hiding
things in the interface — a doctor who edits a URL or calls the API directly
gets the same answer as the dashboard shows them.

  admin  — sees every department (administration and oversight)
  doctor — sees only their own department
  staff  — sees every department (front desk must direct any arriving patient)

A doctor whose account has no department set is treated as unscoped, so an
incomplete account fails open to the current behaviour rather than locking the
consultant out of their own list mid-clinic.
"""
from typing import Optional

from fastapi import HTTPException, status

from app.models.enums import Department, UserRole
from app.models.user import User


def effective_department(
    user: User, requested: Optional[Department] = None
) -> Optional[Department]:
    """The department filter to apply for this user.

    Returns None for "no restriction". A doctor's own department always wins
    over whatever the caller asked for, so a crafted query string cannot widen
    their view.
    """
    if user.role is UserRole.DOCTOR and user.department is not None:
        return user.department
    return requested


def assert_may_access(user: User, department: Optional[Department]) -> None:
    """Guard a single record. Raises 404 rather than 403 on purpose.

    Telling a gynaecologist that an orthopaedic consultation exists but is
    forbidden leaks that the record exists at all; "not found" reveals nothing.
    """
    if user.role is not UserRole.DOCTOR or user.department is None:
        return
    if department is not None and department != user.department:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
