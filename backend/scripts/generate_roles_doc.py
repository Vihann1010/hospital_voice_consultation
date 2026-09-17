"""Regenerate docs/ROLES.txt from the permission catalogue.

The document is written by the code it describes so that it cannot drift.
Every route names the permission it requires, `app/core/permissions.py` maps
permissions to roles, and this script renders that mapping. Nothing here
decides anything — a role gaining a power is a change to the catalogue, and
this file only reports it.

Run after any change to Permission or ROLE_PERMISSIONS. It writes to stdout
so it works the same inside the container, where the docs directory is not
mounted, as it does on a developer's machine:

    docker exec satya-backend python scripts/generate_roles_doc.py > docs/ROLES.txt

The one thing kept by hand is the plain-English wording below. A permission
added without a description is reported loudly rather than printed as its
raw string, because "invoice:cancel" in a document meant for the hospital's
own staff is not an explanation.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.permissions import Permission, ROLE_PERMISSIONS  # noqa: E402
from app.models.enums import UserRole  # noqa: E402

WIDTH = 78

# What each permission means to somebody who does not read code.
DESCRIPTIONS = {
    Permission.PATIENT_READ: "Open a patient's record and search the register",
    Permission.CONSULTATION_READ: "Read consultations, intake summaries and transcripts",
    Permission.REPORT_READ: "Read uploaded investigation reports",
    Permission.PRESCRIPTION_READ: "Read issued prescriptions",
    Permission.AUDIT_READ: "Read the audit trail of who opened and changed what",
    Permission.CONSULTATION_REVIEW: "Sign off a consultation as the treating doctor",
    Permission.COPILOT_USE: "Use the AI copilot: red flags, differentials, suggestions",
    Permission.ORDER_CREATE: "Order investigations",
    Permission.PRESCRIPTION_CREATE: "Write and issue a prescription",
    Permission.PRESCRIPTION_SEND: "Send a prescription to the patient over WhatsApp",
    Permission.TEMPLATE_MANAGE: "Create and edit clinical templates",
    Permission.CLINICAL_DOCUMENT_WRITE: "Write in the Visit Pad and other clinical documents",
    Permission.CLINICAL_DOCUMENT_SIGN: "Sign a clinical document, or sign a corrected version",
    Permission.PAD_LAYOUT_MANAGE: "Change the sections of a department's or the hospital's pad",
    Permission.WARD_CHART: "Record observations and doses, change bed status, move a patient's bed",
    Permission.NURSING_DOCUMENT: "Write and sign the nursing assessment and nursing notes",
    Permission.THEATRE_SCHEDULE: "Book, reschedule and cancel an operation theatre case",
    Permission.THEATRE_RECORD: "Record theatre times: wheel-in, incision, closure, wheel-out",
    Permission.LAB_REGISTER: "Register laboratory tests for a patient",
    Permission.LAB_RESULT_ENTER: "Enter laboratory results and mark samples collected",
    Permission.LAB_RESULT_VERIFY: "Verify laboratory results, and reopen a verified one",
    Permission.LAB_MASTER_MANAGE: "Edit the lab test list, units and reference ranges",
    Permission.DIET_ORDER: "Order, change and stop an inpatient's diet",
    Permission.ACCOUNTS_MANAGE: "Post vouchers, keep the chart of accounts, run and pay consultant payouts",
    Permission.REPORT_UPLOAD: "Upload a scanned or external report against a patient",
    Permission.SYSTEM_ADMIN: "System administration, including staff accounts",
    Permission.MASTER_READ: "Look up consultants and referring doctors",
    Permission.MASTER_MANAGE: "Edit the consultant register and the registration form",
    Permission.PATIENT_REGISTER: "Register a new patient and issue a UHID",
    Permission.VISIT_CREATE: "Open a visit and allot a queue token",
    Permission.APPOINTMENT_READ: "See the appointment diary and the day's queue board",
    Permission.APPOINTMENT_MANAGE: "Book, move and cancel appointments; check patients in",
    Permission.INVOICE_CREATE: "Raise a bill",
    Permission.INVOICE_READ: "Read and reprint a bill",
    Permission.PAYMENT_COLLECT: "Take payment and run the cash drawer",
    Permission.REFUND_ISSUE: "Return money to a patient",
    Permission.INVOICE_CANCEL: "Cancel a bill that was already raised",
    Permission.FINANCE_READ: "See hospital-wide revenue and collection figures",
    Permission.TARIFF_MANAGE: "Change the price list",
    Permission.CLAIM_MANAGE: "Keep insurance policies and TPA claims; put an approved claim on the bill",
}

ROLE_SUMMARY = {
    UserRole.ADMIN: (
        "The system owner.",
        "Everything, including staff accounts and system settings. Held by one or\n"
        "  two people, not used for daily work.",
    ),
    UserRole.MANAGER: (
        "The hospital's money and oversight.",
        "Sees revenue and collections, sets the price list, owns the consultant\n"
        "  register and the registration form, reads the audit trail. Deliberately\n"
        "  cannot work the till or register a patient - oversight is not operation.",
    ),
    UserRole.DOCTOR: (
        "Clinical authority.",
        "Consults, prescribes, orders investigations, uses the copilot, signs off\n"
        "  records. Can cover the counter. Deliberately cannot reprice a service,\n"
        "  refund, cancel a bill, or see hospital-wide revenue - treatment decisions\n"
        "  are not pricing decisions.",
    ),
    UserRole.SUPERVISOR: (
        "The counter's escalation point.",
        "Everything reception does, plus the two actions that undo counter work:\n"
        "  refunds and bill cancellations. No clinical authority.",
    ),
    UserRole.NURSE: (
        "The ward.",
        "Records observations and doses, and writes and signs the nursing\n"
        "  assessment and shift notes. Reads the doctor's notes. Cannot prescribe,\n"
        "  admit, discharge, bill, or sign a doctor's document.",
    ),
    UserRole.LAB: (
        "The laboratory bench.",
        "Registers samples, marks them collected and enters results, including\n"
        "  culture sensitivity. Cannot verify a result, change a reference range,\n"
        "  raise a bill or take payment.",
    ),
    UserRole.RECEPTION: (
        "The front desk.",
        "Registers patients, books appointments, raises bills, takes payment, runs\n"
        "  the cash drawer, uploads reports. Cannot refund, cancel a bill, reprice\n"
        "  a service, or see hospital-wide revenue.",
    ),
}

NOTES = """  * A doctor cannot refund or reprice. If a refund is needed and no supervisor
    is on shift it takes an admin, so create at least one supervisor account
    before go-live.

  * A manager cannot register a patient or take payment. If the same person
    does both jobs, give them two accounts rather than widening the manager
    role.

  * Reception and supervisor both land on the reception terminal at login;
    everyone else lands on the clinical dashboard.

  * Earlier versions had a single 'staff' role. Those users are now
    'reception', with exactly the permissions they held before.

  * Consultant records are separate from logins. A visiting doctor can appear
    on a prescription without ever having an account, and deactivating an
    account does not remove the consultant from the history of patients they
    treated.

  * Ward charting (observations, doses, bed moves) is held by nurses and,
    for now, by doctors, supervisors and reception too, because the ward has
    been run on those accounts. The nursing documents themselves are nurses'
    only. Decide whether reception should keep charting once nurse accounts
    exist.

  * A nurse signs in to the ward terminal, not the clinical dashboard.

  * A signed clinical document is never edited, by anyone. A correction is a
    new signed version with a reason, and the original stays readable. This
    holds for admins too.

  * A doctor can rearrange their own Visit Pad. Changing the pad for a whole
    department or the hospital is an admin action, because it changes what
    prints on every doctor's documents.

  * A lab report goes out only when a doctor verifies it. The lab role types
    results; the pathologist's account (a doctor) verifies them. A test whose
    reference ranges were edited cannot be verified until a doctor reviews
    the ranges again.

  * A lab technician signs in to the laboratory terminal (/lab).

  * A receptionist may book and cancel an appointment but not cancel a bill.
    Freeing a slot costs the hospital nothing; unpicking a raised invoice is
    an accounting act, which is why it sits with the supervisor.

  * TPA claims are worked at the counter: policies, pre-authorisation, claim
    status, and putting the approved amount on the bill. Recording what the
    TPA or insurer actually paid, with TDS and disallowances, is accounts
    work and needs the finance PIN.

  * A consultant's payout share is set only on the Accounts screen, where the
    change is audited; the consultant register does not change it."""


def describe(permission: Permission) -> str:
    try:
        return DESCRIPTIONS[permission]
    except KeyError:
        raise SystemExit(
            f"No plain-English description for {permission.value!r}.\n"
            f"Add one to DESCRIPTIONS in {Path(__file__).name} before regenerating — "
            "this document is read by the hospital's own staff, not by developers."
        )


def render() -> str:
    ordered = list(Permission)
    lines = [
        "=" * WIDTH,
        "SATYA HOSPITAL PLATFORM - STAFF ROLES AND WHAT EACH ONE CAN DO",
        "=" * WIDTH,
        "",
        f"Generated {date.today():%Y-%m-%d} from app/core/permissions.py,",
        "which is the single place these rules live. Every API route names the",
        "permission it needs, so this document and the running system cannot",
        "disagree. Regenerate it with scripts/generate_roles_doc.py after any",
        "change to the catalogue.",
        "",
        f"{len(UserRole)} roles, {len(ordered)} permissions.",
        "",
    ]

    for role in UserRole:
        held = ROLE_PERMISSIONS.get(role, set())
        title, summary = ROLE_SUMMARY[role]
        lines += [
            "-" * WIDTH,
            f"{role.value.upper()}  -  {title}",
            "-" * WIDTH,
            f"  {summary}",
            "",
            f"  CAN ({len(held)} of {len(ordered)}):",
        ]
        lines += [f"    + {describe(p)}" for p in ordered if p in held]
        missing = [p for p in ordered if p not in held]
        if missing:
            lines += ["", "  CANNOT:"]
            lines += [f"    - {describe(p)}" for p in missing]
        lines.append("")

    # --- the matrix ---------------------------------------------------------
    label_width = max(len(describe(p)) for p in ordered) + 2
    header = " " * label_width + "".join(f"{role.value[:9]:>11}" for role in UserRole)
    rule = " " * label_width + "".join(f"{'-' * 9:>11}" for _ in UserRole)
    lines += ["=" * WIDTH, "AT A GLANCE", "=" * WIDTH, "", header, rule]
    for permission in ordered:
        row = f"{describe(permission):<{label_width}}"
        for role in UserRole:
            mark = "YES" if permission in ROLE_PERMISSIONS.get(role, set()) else "."
            row += f"{mark:>11}"
        lines.append(row)

    lines += ["", "=" * WIDTH, "NOTES", "=" * WIDTH, "", NOTES, ""]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(), encoding="utf-8")
        print(
            f"Wrote {target} "
            f"({len(list(Permission))} permissions, {len(list(UserRole))} roles).",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(render())
