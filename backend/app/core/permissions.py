"""Role permission matrix.

RBAC was previously expressed as ad-hoc role lists on each route. Centralising
it means the rules can be read in one place, tested as data, and rendered in
the documentation without trawling the routers.

Roles:
  admin      — everything, including user and system administration
  manager    — the hospital's money: revenue, the price list, the audit trail.
               No clinical authority and no till access.
  doctor     — full clinical authority: prescribe, order, sign off, use the
               copilot. Deliberately holds no pricing power and cannot refund.
  supervisor — the counter's escalation: refunds and cancellations, on top of
               everything reception does. No clinical authority.
  reception  — the front desk: register, bill, collect, upload reports.
  nurse      — the ward: observations, doses, and the nursing documents.
               No prescribing, no discharge, no till.
  lab        — the laboratory bench: registers samples and enters results.
               A result goes out only once a doctor (the pathologist)
               verifies it.

The three elevated roles are separated on purpose. Seeing hospital revenue,
returning money to a patient, and carrying clinical responsibility are
different kinds of trust, and a doctor repricing a service is not one of them.
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
    # The clinical record. Writing a pad and signing it are separate, because
    # Part 3 brings nursing forms where the person charting is not the person
    # who signs off, and because a draft is working notes while a signature is
    # a statement the hospital stands behind.
    CLINICAL_DOCUMENT_WRITE = "clinical_document:write"
    CLINICAL_DOCUMENT_SIGN = "clinical_document:sign"
    # What every doctor's pad looks like. A personal layout needs only write
    # access; changing the department's or hospital's changes a legal document
    # for everyone, so it is administration.
    PAD_LAYOUT_MANAGE = "pad_layout:manage"
    # The ward's everyday record: observations, doses given, bed status,
    # transfers and ward charges. Until now this was guarded by the
    # permission to read a patient, which every account holds.
    WARD_CHART = "ward:chart"
    # The nurse's own documents — the initial assessment and each shift's
    # note — written and signed by the nurse, not drafted for a doctor.
    NURSING_DOCUMENT = "nursing_document:write"
    # The operation theatre. Booking and cancelling a case is the doctor's;
    # recording its theatre times is shared with the theatre nurses who are
    # standing at the door when they happen.
    THEATRE_SCHEDULE = "theatre:schedule"
    THEATRE_RECORD = "theatre:record"
    # The laboratory. Registering a test is counter and ward work; typing
    # results is the technician's; verifying them puts the hospital's name
    # to a report and is the pathologist's alone. The test list carries the
    # reference ranges every flag is computed from, so it is clinical
    # administration rather than a price list.
    LAB_REGISTER = "lab:register"
    LAB_RESULT_ENTER = "lab:result"
    LAB_RESULT_VERIFY = "lab:verify"
    LAB_MASTER_MANAGE = "lab:master"
    # Operational
    REPORT_UPLOAD = "report:upload"
    SYSTEM_ADMIN = "system:admin"
    # The consultant and referral registers. Reading one is everyday work at
    # the counter; editing one changes what patients are charged and what a
    # prescription claims about who signed it.
    MASTER_READ = "master:read"
    MASTER_MANAGE = "master:manage"
    # Front desk
    PATIENT_REGISTER = "patient:register"
    VISIT_CREATE = "visit:create"
    INVOICE_CREATE = "invoice:create"
    INVOICE_READ = "invoice:read"
    PAYMENT_COLLECT = "payment:collect"
    # The diary and the board. Reading them is everyday counter work;
    # booking, moving and cancelling somebody's slot is the same authority as
    # opening a visit, which is why it sits beside it rather than above it.
    APPOINTMENT_READ = "appointment:read"
    APPOINTMENT_MANAGE = "appointment:manage"
    # Money leaving the till, and hospital-wide revenue, are not front-desk work
    REFUND_ISSUE = "refund:issue"
    INVOICE_CANCEL = "invoice:cancel"
    FINANCE_READ = "finance:read"
    TARIFF_MANAGE = "tariff:manage"


_READ_ONLY: Set[Permission] = {
    Permission.PATIENT_READ,
    Permission.CONSULTATION_READ,
    Permission.REPORT_READ,
    Permission.PRESCRIPTION_READ,
    # Choosing a consultant is part of registering a visit, so reading the
    # register is everyday work rather than administration.
    Permission.MASTER_READ,
    # A doctor needs to see whose morning they are looking at, and a manager
    # needs to see how full the clinic is. Neither books.
    Permission.APPOINTMENT_READ,
}

# The front desk registers patients, bills them and takes payment all day.
# It does not issue refunds, change the price list, or see hospital revenue.
_FRONT_DESK: Set[Permission] = {
    Permission.PATIENT_REGISTER,
    Permission.VISIT_CREATE,
    Permission.INVOICE_CREATE,
    # Reading and reprinting the bill just raised at the counter. Distinct from
    # FINANCE_READ, which is hospital-wide revenue and is not front-desk data.
    Permission.INVOICE_READ,
    Permission.PAYMENT_COLLECT,
    Permission.APPOINTMENT_MANAGE,
    # Sending a patient's sample to the laboratory from the counter.
    Permission.LAB_REGISTER,
    # The ward has been run on reception and supervisor accounts, so they
    # keep charting rather than finding the ward locked on the day this
    # ships. Whether they should is a decision for the hospital.
    Permission.WARD_CHART,
}

# Clinical authority. Notably absent: the price list, hospital revenue, and
# money leaving the till — a doctor decides treatment, not what it costs.
_CLINICAL: Set[Permission] = _READ_ONLY | _FRONT_DESK | {
    Permission.CONSULTATION_REVIEW,
    Permission.COPILOT_USE,
    Permission.ORDER_CREATE,
    Permission.PRESCRIPTION_CREATE,
    Permission.PRESCRIPTION_SEND,
    Permission.TEMPLATE_MANAGE,
    Permission.REPORT_UPLOAD,
    Permission.CLINICAL_DOCUMENT_WRITE,
    Permission.CLINICAL_DOCUMENT_SIGN,
    Permission.THEATRE_SCHEDULE,
    Permission.THEATRE_RECORD,
    Permission.LAB_RESULT_ENTER,
    Permission.LAB_RESULT_VERIFY,
    Permission.LAB_MASTER_MANAGE,
}

# The counter's escalation path: the same work reception does, plus the two
# actions that undo it. No clinical authority.
_SUPERVISORY: Set[Permission] = _READ_ONLY | _FRONT_DESK | {
    Permission.REPORT_UPLOAD,
    Permission.REFUND_ISSUE,
    Permission.INVOICE_CANCEL,
}

# Management sees the money and sets the price list, but does not work the
# till and holds no clinical authority.
_MANAGEMENT: Set[Permission] = _READ_ONLY | {
    Permission.INVOICE_READ,
    Permission.FINANCE_READ,
    Permission.TARIFF_MANAGE,
    Permission.AUDIT_READ,
    # A consultant's free-follow-up window and fee decide what a patient is
    # charged, which makes the register a pricing control.
    Permission.MASTER_MANAGE,
}

# The ward. Reads the record, charts on it, and writes and signs the
# nursing documents. The nursing documents are nobody else's: a doctor
# reads the nursing assessment but does not sign it.
_NURSING: Set[Permission] = _READ_ONLY | {
    Permission.WARD_CHART,
    Permission.NURSING_DOCUMENT,
    Permission.THEATRE_RECORD,
    # Nurses scan signed consent forms and referral letters on the ward.
    Permission.REPORT_UPLOAD,
    # Sending an inpatient's sample to the laboratory. Billed to the stay:
    # a nurse raises no invoice.
    Permission.LAB_REGISTER,
}

# The laboratory bench. Registers samples and types results; cannot verify
# them, change a reference range, raise a bill or take money.
_LAB: Set[Permission] = _READ_ONLY | {
    Permission.LAB_REGISTER,
    Permission.LAB_RESULT_ENTER,
    Permission.REPORT_UPLOAD,
}

ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.ADMIN: set(Permission),
    UserRole.MANAGER: _MANAGEMENT,
    UserRole.DOCTOR: _CLINICAL,
    UserRole.SUPERVISOR: _SUPERVISORY,
    # The front desk moves paper and money all day, but cannot refund,
    # cancel, reprice, or see hospital-wide revenue.
    UserRole.RECEPTION: _READ_ONLY | _FRONT_DESK | {Permission.REPORT_UPLOAD},
    UserRole.NURSE: _NURSING,
    UserRole.LAB: _LAB,
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
