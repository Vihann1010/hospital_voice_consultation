"""Role permission matrix.

RBAC was previously expressed as ad-hoc role lists on each route. Centralising
it means the rules can be read in one place, tested as data, and rendered in
the documentation without trawling the routers.

Roles:
  admin   — everything, including user and system administration
  doctor  — full clinical authority: prescribe, order, sign off, use the copilot
  staff   — front desk: read records, upload reports; no clinical authority
"""
from enum import Enum
from typing import Dict, Set

from app.models.enums import UserRole


class Permission(str, Enum):
    # Reading
    PATIENT_READ = "patient:read"
    CONSULTATION_READ = "consultation:read"
    REPORT_READ = "report:read"
    PRESCRIPTION_READ = "prescription:read"
    AUDIT_READ = "audit:read"
    # Clinical authority
    CONSULTATION_REVIEW = "consultation:review"
    COPILOT_USE = "copilot:use"
    ORDER_CREATE = "order:create"
    PRESCRIPTION_CREATE = "prescription:create"
    PRESCRIPTION_SEND = "prescription:send"
    TEMPLATE_MANAGE = "template:manage"
    # Operational
    REPORT_UPLOAD = "report:upload"
    SYSTEM_ADMIN = "system:admin"
    # Front desk
    PATIENT_REGISTER = "patient:register"
    VISIT_CREATE = "visit:create"
    INVOICE_CREATE = "invoice:create"
    PAYMENT_COLLECT = "payment:collect"
    # Money leaving the till, and hospital-wide revenue, are not front-desk work
    REFUND_ISSUE = "refund:issue"
    FINANCE_READ = "finance:read"
    TARIFF_MANAGE = "tariff:manage"


_READ_ONLY: Set[Permission] = {
    Permission.PATIENT_READ,
    Permission.CONSULTATION_READ,
    Permission.REPORT_READ,
    Permission.PRESCRIPTION_READ,
}

# The front desk registers patients, bills them and takes payment all day.
# It does not issue refunds, change the price list, or see hospital revenue.
_FRONT_DESK: Set[Permission] = {
    Permission.PATIENT_REGISTER,
    Permission.VISIT_CREATE,
    Permission.INVOICE_CREATE,
    Permission.PAYMENT_COLLECT,
}

_CLINICAL: Set[Permission] = _READ_ONLY | _FRONT_DESK | {
    Permission.REFUND_ISSUE,
    Permission.FINANCE_READ,
    Permission.TARIFF_MANAGE,
    Permission.CONSULTATION_REVIEW,
    Permission.COPILOT_USE,
    Permission.ORDER_CREATE,
    Permission.PRESCRIPTION_CREATE,
    Permission.PRESCRIPTION_SEND,
    Permission.TEMPLATE_MANAGE,
    Permission.REPORT_UPLOAD,
}

ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.ADMIN: set(Permission),
    UserRole.DOCTOR: _CLINICAL,
    # Front desk can move paper and money around but holds no clinical
    # authority, and cannot refund, reprice or see hospital-wide revenue.
    UserRole.STAFF: _READ_ONLY | _FRONT_DESK | {Permission.REPORT_UPLOAD},
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def permissions_for(role: UserRole) -> Set[Permission]:
    return set(ROLE_PERMISSIONS.get(role, set()))


def matrix() -> Dict[str, Dict[str, bool]]:
    """Serialisable view used by the docs endpoint and the front end."""
    return {
        permission.value: {
            role.value: has_permission(role, permission) for role in UserRole
        }
        for permission in Permission
    }
