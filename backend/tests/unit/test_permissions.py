"""RBAC matrix — the rule that front desk holds no clinical authority."""
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


@pytest.mark.parametrize("permission", CLINICAL_ONLY)
def test_staff_hold_no_clinical_authority(permission):
    assert not has_permission(UserRole.STAFF, permission)


@pytest.mark.parametrize("permission", CLINICAL_ONLY)
def test_doctors_hold_clinical_authority(permission):
    assert has_permission(UserRole.DOCTOR, permission)


def test_admin_only_permissions():
    for permission in (Permission.SYSTEM_ADMIN, Permission.AUDIT_READ):
        assert has_permission(UserRole.ADMIN, permission)
        assert not has_permission(UserRole.DOCTOR, permission)
        assert not has_permission(UserRole.STAFF, permission)


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
