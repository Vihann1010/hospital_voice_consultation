"""RBAC matrix — the rule that only doctors (and admin) hold clinical authority."""
import pytest

from app.core.permissions import Permission, has_permission, matrix, permissions_for
from app.models.enums import UserRole

pytestmark = pytest.mark.unit

CLINICAL_ONLY = [
    Permission.PRESCRIPTION_CREATE,
    Permission.PRESCRIPTION_SEND,
    Permission.ORDER_CREATE,
    Permission.CONSULTATION_REVIEW,
    Permission.COPILOT_USE,
    Permission.TEMPLATE_MANAGE,
]

# Every role that works in the hospital without carrying clinical
# responsibility: the counter, its escalation, and the people who see the money.
NON_CLINICAL_ROLES = [UserRole.RECEPTION, UserRole.SUPERVISOR, UserRole.MANAGER, UserRole.LAB]


def _holders(permission):
    return {role for role in UserRole if has_permission(role, permission)}


@pytest.mark.parametrize("role", NON_CLINICAL_ROLES)
@pytest.mark.parametrize("permission", CLINICAL_ONLY)
def test_non_clinical_roles_hold_no_clinical_authority(role, permission):
    assert not has_permission(role, permission)


@pytest.mark.parametrize("permission", CLINICAL_ONLY)
def test_doctors_hold_clinical_authority(permission):
    assert has_permission(UserRole.DOCTOR, permission)


@pytest.mark.parametrize("permission", CLINICAL_ONLY)
def test_clinical_authority_is_held_only_by_doctor_and_admin(permission):
    # Catches a clinical permission leaking to any role, including one added later.
    assert _holders(permission) == {UserRole.ADMIN, UserRole.DOCTOR}


def test_system_admin_is_admin_only():
    assert _holders(Permission.SYSTEM_ADMIN) == {UserRole.ADMIN}


def test_audit_trail_is_admin_and_management_only():
    # Management owns the audit trail alongside revenue; nobody on the clinical
    # or counter side reads it.
    assert _holders(Permission.AUDIT_READ) == {UserRole.ADMIN, UserRole.MANAGER}


def test_every_role_can_read_records():
    for role in UserRole:
        assert has_permission(role, Permission.PATIENT_READ)


def test_admin_is_a_superset_of_every_role():
    admin = permissions_for(UserRole.ADMIN)
    for role in UserRole:
        assert permissions_for(role) <= admin


def test_matrix_covers_every_permission_and_role():
    rendered = matrix()
    assert set(rendered) == {permission.value for permission in Permission}
    for roles in rendered.values():
        assert set(roles) == {role.value for role in UserRole}
