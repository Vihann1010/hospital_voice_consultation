"""The reconciliation reports: the figures accounts checks everything else against.

Seven reports, all built on the same rules as the front-office six so that
their totals tie to each other — the gate for this part is arithmetic:

* **Collection summary** — every operator's takings split by payment mode.
  Its cash column plus wallet deposits equals the daily closing's cash in.
* **Consultant-wise billing** and **department billing** — the same bills as
  the invoice list, grouped differently; each totals to the invoice list's net.
* **Patient list** — who was registered.
* **Wallet report** — every patient's credit moving through a range, checked
  against the stored running balance.
* **Inpatient balances** and **inpatient ledger** — what each admission owes.

**Admission advances.** An advance is a receipted deposit into the patient's
wallet, tagged to the stay, and settles the final bill from there; it is
counted in the drawer once, on the day it is taken, in the mode it was paid.
Advances typed on the admission form before receipts existed never passed
through a till; they are shown in their own "not receipted" column rather
than dropped or counted as collected.
"""
import uuid
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import day_bounds, to_local
from app.models.consultant import Consultant
from app.models.emr import Invoice, Payment, PatientWallet, Visit, WalletEntry
from app.models.enums import AdmissionStatus, InvoiceStatus, PaymentMode, WalletEntryKind
from app.models.ipd import Admission, AdmissionCharge, BedOccupancy
from app.models.patient import Patient
from app.reports.definitions import Column, ColumnType, ReportSpec, register
from app.reports.ledger_rules import running_ledger, wallet_row
from app.reports.sources import invoice_sources

M = ColumnType.MONEY
N = ColumnType.NUMBER
D = ColumnType.DATE
DT = ColumnType.DATETIME
S = ColumnType.STATUS

UNATTRIBUTED = "Not attributed"


def _window(date_from: date, date_to: date):
    start, _ = day_bounds(date_from)
    _, end = day_bounds(date_to)
    return start, end


def _local_day(moment: datetime) -> date:
    return to_local(moment).date()


# ------------------------------------------------------- collection summary
_MODE_COLUMN = {
    PaymentMode.CASH: "cash_paise",
    PaymentMode.CARD: "card_paise",
    PaymentMode.UPI: "upi_paise",
    PaymentMode.NET_BANKING: "net_banking_paise",
    PaymentMode.CHEQUE: "cheque_paise",
    PaymentMode.INSURANCE: "insurance_paise",
}

COLLECTION_SUMMARY = ReportSpec(
    key="collection-summary",
    title="Collection summary",
    description="Every operator's takings by payment mode, for cash handover.",
    columns=[
        Column("operator", "Operator"),
        Column("cash_paise", "Cash", M, total=True),
        Column("card_paise", "Card", M, total=True),
        Column("upi_paise", "UPI", M, total=True),
        Column("net_banking_paise", "Net banking", M, total=True),
        Column("cheque_paise", "Cheque", M, total=True),
        # Not money: the insurer's share put on the bill. Kept out of Collected.
        Column("insurance_paise", "Booked to insurers", M, total=True, default_visible=False),
        Column("wallet_deposits_paise", "Advances taken", M, total=True),
        Column("cash_advances_paise", "Advances in cash", M, total=True, default_visible=False),
        Column("collected_paise", "Collected", M, total=True),
        Column("refunds_paise", "Refunds", M, total=True),
        Column("advances_returned_paise", "Advances returned", M, total=True),
        Column("net_paise", "Net", M, total=True),
        Column("cash_out_paise", "Cash out", M, total=True, default_visible=False),
        Column("waived_paise", "Waived", M, total=True, default_visible=False),
        Column("receipts", "Receipts", N, total=True, default_visible=False),
    ],
)


async def _collection_summary(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    """Collected is money that arrived; a waiver is not money and is shown apart.

    Same exclusions as the cash ledger: struck receipts never happened, and a
    bill settled from the wallet was counted when the advance was deposited.
    """
    start, end = _window(date_from, date_to)
    operators: Dict[str, Dict[str, Any]] = {}

    def row(name: str) -> Dict[str, Any]:
        return operators.setdefault(name or "—", {
            "operator": name or "—", **{column: 0 for column in _MODE_COLUMN.values()},
            "wallet_deposits_paise": 0, "cash_advances_paise": 0, "refunds_paise": 0,
            "advances_returned_paise": 0,
            "cash_out_paise": 0, "waived_paise": 0, "receipts": 0,
        })

    payments = (await session.execute(
        select(Payment).where(
            Payment.received_at >= start, Payment.received_at < end,
            Payment.cancelled_at.is_(None), Payment.mode != PaymentMode.WALLET,
        )
    )).scalars()
    for payment in payments:
        target = row(payment.received_by_name)
        amount = abs(payment.amount_paise)
        if payment.mode is PaymentMode.WAIVER:
            target["waived_paise"] += -amount if payment.is_refund else amount
            continue
        if payment.is_refund:
            target["refunds_paise"] += amount
            if payment.mode is PaymentMode.CASH:
                target["cash_out_paise"] += amount
            continue
        target["receipts"] += 1
        target[_MODE_COLUMN.get(payment.mode, "insurance_paise")] += amount

    entries = (await session.execute(
        select(WalletEntry).where(
            WalletEntry.created_at >= start, WalletEntry.created_at < end,
            WalletEntry.kind.in_((WalletEntryKind.DEPOSIT, WalletEntryKind.WITHDRAWAL)),
        )
    )).scalars()
    for entry in entries:
        target = row(entry.created_by_name)
        in_cash = entry.mode in (None, PaymentMode.CASH)
        if entry.amount_paise > 0:
            target["wallet_deposits_paise"] += entry.amount_paise
            target["receipts"] += 1
            if in_cash:
                target["cash_advances_paise"] += entry.amount_paise
        else:
            target["advances_returned_paise"] += abs(entry.amount_paise)
            if in_cash:
                target["cash_out_paise"] += abs(entry.amount_paise)

    rows = []
    for target in operators.values():
        target["collected_paise"] = sum(
            target[c] for c in _MODE_COLUMN.values() if c != "insurance_paise"
        ) + target["wallet_deposits_paise"]
        target["net_paise"] = target["collected_paise"] - target["refunds_paise"] - target["advances_returned_paise"]
        rows.append(target)
    rows.sort(key=lambda item: item["operator"])
    return rows


# ------------------------------------------------------- consultant billing
async def _live_invoices(session: AsyncSession, date_from: date, date_to: date):
    """Bills raised in the range and not cancelled — the invoice list's basis."""
    start, end = _window(date_from, date_to)
    return (await session.execute(
        select(Invoice, Visit, Consultant)
        .outerjoin(Visit, Visit.id == Invoice.visit_id)
        .outerjoin(Consultant, Consultant.id == Invoice.consultant_id)
        .where(Invoice.created_at >= start, Invoice.created_at < end,
               Invoice.status != InvoiceStatus.CANCELLED)
    )).all()


CONSULTANT_BILLING = ReportSpec(
    key="consultant-billing",
    title="Consultant-wise billing",
    description="Bills raised under each consultant, what was collected and what is still owed.",
    columns=[
        Column("consultant", "Consultant"),
        Column("department", "Department", S),
        Column("bills", "Bills", N, total=True),
        Column("patients", "Patients", N),
        Column("gross_paise", "Gross", M, total=True),
        Column("discount_paise", "Discount", M, total=True),
        Column("net_paise", "Net", M, total=True),
        Column("paid_paise", "Paid", M, total=True),
        Column("balance_paise", "Balance", M, total=True),
        Column("refunded_paise", "Refunded", M, total=True, default_visible=False),
    ],
)


async def _consultant_billing(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    found = await _live_invoices(session, date_from, date_to)
    refunds: Dict[uuid.UUID, int] = {}
    if found:
        for invoice_id, amount in (await session.execute(
            select(Payment.invoice_id, func.coalesce(func.sum(Payment.amount_paise), 0))
            .where(Payment.invoice_id.in_([invoice.id for invoice, _, _ in found]),
                   Payment.is_refund.is_(True), Payment.cancelled_at.is_(None))
            .group_by(Payment.invoice_id)
        )).all():
            refunds[invoice_id] = abs(int(amount or 0))

    groups: Dict[str, Dict[str, Any]] = {}
    patients: Dict[str, set] = defaultdict(set)
    for invoice, visit, consultant in found:
        name = consultant.full_name if consultant else (invoice.doctor_name or (visit.doctor_name if visit else "")) or UNATTRIBUTED
        department = (consultant.department.value if consultant and consultant.department
                      else visit.department.value if visit else "")
        target = groups.setdefault(name, {
            "consultant": name, "department": department, "bills": 0, "gross_paise": 0,
            "discount_paise": 0, "net_paise": 0, "paid_paise": 0, "balance_paise": 0, "refunded_paise": 0,
        })
        target["bills"] += 1
        target["gross_paise"] += invoice.gross_paise
        target["discount_paise"] += invoice.discount_paise
        target["net_paise"] += invoice.total_paise
        target["paid_paise"] += invoice.paid_paise
        target["balance_paise"] += invoice.total_paise - invoice.paid_paise
        target["refunded_paise"] += refunds.get(invoice.id, 0)
        patients[name].add(invoice.patient_id)
    rows = []
    for name, target in groups.items():
        target["patients"] = len(patients[name])
        rows.append(target)
    rows.sort(key=lambda item: (-item["net_paise"], item["consultant"]))
    return rows


# ------------------------------------------------------- department billing
DEPARTMENT_BILLING = ReportSpec(
    key="department-billing",
    title="Department and day-wise billing",
    description="What each department billed each day, and from which desk.",
    columns=[
        Column("day", "Date", D),
        Column("department", "Department", S),
        Column("source", "From"),
        Column("bills", "Bills", N, total=True),
        Column("gross_paise", "Gross", M, total=True),
        Column("discount_paise", "Discount", M, total=True),
        Column("net_paise", "Net", M, total=True),
    ],
)


async def _department_billing(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    found = await _live_invoices(session, date_from, date_to)
    sources = await invoice_sources(session, [invoice for invoice, _, _ in found])
    admission_departments: Dict[uuid.UUID, str] = {}
    ipd_ids = [invoice.id for invoice, _, _ in found if sources.get(invoice.id) == "IPD"]
    if ipd_ids:
        for invoice_id, department in (await session.execute(
            select(Admission.final_invoice_id, Admission.department).where(Admission.final_invoice_id.in_(ipd_ids))
        )).all():
            admission_departments[invoice_id] = department.value
    groups: Dict[tuple, Dict[str, Any]] = {}
    for invoice, visit, consultant in found:
        department = (admission_departments.get(invoice.id)
                      or (visit.department.value if visit else None)
                      or (consultant.department.value if consultant and consultant.department else None)
                      or "unassigned")
        day = _local_day(invoice.issued_at or invoice.created_at) if invoice.issued_at else _local_day(invoice.created_at)
        key = (day, department, sources.get(invoice.id, ""))
        target = groups.setdefault(key, {"day": day, "department": department, "source": key[2],
                                         "bills": 0, "gross_paise": 0, "discount_paise": 0, "net_paise": 0})
        target["bills"] += 1
        target["gross_paise"] += invoice.gross_paise
        target["discount_paise"] += invoice.discount_paise
        target["net_paise"] += invoice.total_paise
    return sorted(groups.values(), key=lambda item: (item["day"], item["department"], item["source"]), reverse=True)


# ------------------------------------------------------------- patient list
PATIENT_LIST = ReportSpec(
    key="patient-list",
    title="Patient list",
    description="Patients registered in the period, with how often they have visited.",
    permission="patient:read",
    columns=[
        Column("registered_on", "Registered", D),
        Column("uhid", "UHID"),
        Column("name", "Patient"),
        Column("age_sex", "Age / sex"),
        Column("phone", "Phone"),
        Column("city", "City", default_visible=False),
        Column("category", "Category", default_visible=False),
        Column("visits", "Visits", N, total=True),
        Column("last_visit", "Last visit", D),
    ],
)


async def _patient_list(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)
    visits = (
        select(Visit.patient_id, func.count(Visit.id).label("visits"), func.max(Visit.visit_date).label("last_visit"))
        .where(Visit.cancelled_at.is_(None)).group_by(Visit.patient_id).subquery()
    )
    found = (await session.execute(
        select(Patient, visits.c.visits, visits.c.last_visit)
        .outerjoin(visits, visits.c.patient_id == Patient.id)
        .where(Patient.created_at >= start, Patient.created_at < end)
        .order_by(Patient.created_at.desc())
    )).all()
    return [{
        "registered_on": _local_day(patient.created_at),
        "uhid": patient.uhid or "",
        "name": patient.name,
        "age_sex": f"{patient.age} / {patient.gender.value[:1].upper()}",
        "phone": patient.phone_number,
        "city": patient.city or "",
        "category": patient.category or "",
        "visits": int(count or 0),
        "last_visit": last,
    } for patient, count, last in found]


# ------------------------------------------------------------ wallet report
WALLET_REPORT = ReportSpec(
    key="wallet-report",
    title="Patient wallet report",
    description="Each patient's advance credit over the period: opening, movements, closing.",
    columns=[
        Column("patient_name", "Patient"),
        Column("uhid", "UHID"),
        Column("opening_paise", "Opening", M, total=True),
        Column("deposits_paise", "Deposited", M, total=True),
        Column("refund_credits_paise", "Refunds kept", M, total=True),
        Column("applied_paise", "Spent on bills", M, total=True),
        Column("withdrawn_paise", "Paid back", M, total=True),
        Column("adjustments_paise", "Adjusted", M, total=True, default_visible=False),
        Column("closing_paise", "Closing", M, total=True),
        Column("current_paise", "Balance today", M, total=True, default_visible=False),
        Column("check", "Check"),
    ],
)


async def _wallet_report(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)
    entries = (await session.execute(
        select(WalletEntry).where(WalletEntry.created_at < end)
        .order_by(WalletEntry.patient_id, WalletEntry.created_at, WalletEntry.id)
    )).scalars()
    per_patient: Dict[uuid.UUID, Dict[str, list]] = defaultdict(lambda: {"before": [], "within": []})
    for entry in entries:
        bucket = "before" if entry.created_at < start else "within"
        per_patient[entry.patient_id][bucket].append({
            "kind": entry.kind.value, "amount_paise": entry.amount_paise,
            "balance_after_paise": entry.balance_after_paise,
        })
    if not per_patient:
        return []
    ids = list(per_patient)
    patients = {p.id: p for p in (await session.execute(select(Patient).where(Patient.id.in_(ids)))).scalars()}
    balances = {w.patient_id: w.balance_paise for w in
                (await session.execute(select(PatientWallet).where(PatientWallet.patient_id.in_(ids)))).scalars()}
    rows = []
    for patient_id, parts in per_patient.items():
        figures = wallet_row(parts["before"], parts["within"])
        if not parts["within"] and figures["closing_paise"] == 0:
            continue
        patient = patients.get(patient_id)
        rows.append({
            "patient_name": patient.name if patient else "",
            "uhid": (patient.uhid or "") if patient else "",
            **figures,
            "current_paise": balances.get(patient_id, 0),
        })
    rows.sort(key=lambda item: (item["check"] == "", -item["closing_paise"], item["patient_name"]))
    return rows


# ------------------------------------------------------- inpatient balances
INPATIENT_BALANCES = ReportSpec(
    key="inpatient-balances",
    title="Inpatient balances",
    description="Every patient in the hospital on the day, with charges so far and what is owed.",
    single_day=True,
    columns=[
        Column("ward", "Ward"),
        Column("bed", "Bed"),
        Column("ip_number", "IP number"),
        Column("patient_name", "Patient"),
        Column("admitted_at", "Admitted", DT, default_visible=False),
        Column("days", "Days", N),
        Column("charges_paise", "Charges so far", M, total=True),
        Column("advance_paise", "Advance held", M, total=True),
        Column("unreceipted_paise", "Old advance, not receipted", M, total=True),
        Column("final_bill_paise", "Final bill", M, total=True),
        Column("paid_paise", "Paid on final bill", M, total=True),
        Column("balance_paise", "Balance", M, total=True),
        Column("status", "Status", S),
    ],
)


async def _inpatient_balances(
    session: AsyncSession, *, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = day_bounds(date_to)
    found = (await session.execute(
        select(Admission, Patient).join(Patient, Patient.id == Admission.patient_id)
        .where(Admission.status != AdmissionStatus.CANCELLED, Admission.admitted_at < end,
               or_(Admission.discharged_at.is_(None), Admission.discharged_at >= start))
    )).all()
    if not found:
        return []
    ids = [admission.id for admission, _ in found]
    charges = dict((await session.execute(
        select(AdmissionCharge.admission_id, func.coalesce(func.sum(AdmissionCharge.total_paise), 0))
        .where(AdmissionCharge.admission_id.in_(ids), AdmissionCharge.charged_on <= date_to)
        .group_by(AdmissionCharge.admission_id)
    )).all())
    places: Dict[uuid.UUID, BedOccupancy] = {}
    for occupancy in (await session.execute(
        select(BedOccupancy).where(BedOccupancy.admission_id.in_(ids), BedOccupancy.started_at < end)
        .order_by(BedOccupancy.started_at)
    )).scalars():
        places[occupancy.admission_id] = occupancy
    invoices = {invoice.id: invoice for invoice in (await session.execute(
        select(Invoice).where(Invoice.id.in_([a.final_invoice_id for a, _ in found if a.final_invoice_id]))
    )).scalars()} if any(a.final_invoice_id for a, _ in found) else {}

    from app.services.ipd_service import IPDService

    ipd = IPDService(session)
    rows = []
    for admission, patient in found:
        place = places.get(admission.id)
        invoice = invoices.get(admission.final_invoice_id)
        live_invoice = invoice is not None and invoice.status is not InvoiceStatus.CANCELLED
        charged = int(charges.get(admission.id, 0) or 0)
        position = await ipd.advance_position(admission)
        if live_invoice:
            balance = invoice.total_paise - invoice.paid_paise
        else:
            balance = charged - position["credit_paise"]
        rows.append({
            "ward": place.ward_name if place else "",
            "bed": place.bed_label if place else "",
            "ip_number": admission.ip_number,
            "patient_name": patient.name,
            "admitted_at": to_local(admission.admitted_at),
            "days": (date_to - _local_day(admission.admitted_at)).days + 1,
            "charges_paise": charged,
            "advance_paise": position["available_paise"],
            "unreceipted_paise": position["unreceipted_paise"],
            "final_bill_paise": invoice.total_paise if live_invoice else 0,
            "paid_paise": invoice.paid_paise if live_invoice else 0,
            "balance_paise": balance,
            "status": admission.status.value,
        })
    rows.sort(key=lambda item: (item["ward"] or "~", item["bed"] or "~", item["ip_number"]))
    return rows


# --------------------------------------------------------- inpatient ledger
INPATIENT_LEDGER = ReportSpec(
    key="inpatient-ledger",
    title="Inpatient ledger",
    description="Each admission's charges, advance, discount and payments with a running balance.",
    columns=[
        Column("ip_number", "IP number"),
        Column("patient_name", "Patient"),
        Column("on", "Date", D),
        Column("particulars", "Particulars"),
        Column("debit_paise", "Charged", M, total=True),
        Column("credit_paise", "Received / allowed", M, total=True),
        Column("balance_paise", "Balance", M),
    ],
)


async def _inpatient_ledger(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)
    touched = set((await session.execute(
        select(AdmissionCharge.admission_id).where(AdmissionCharge.charged_on >= date_from,
                                                   AdmissionCharge.charged_on <= date_to)
    )).scalars())
    touched |= set((await session.execute(
        select(Admission.id).where(Admission.admitted_at >= start, Admission.admitted_at < end)
    )).scalars())
    touched |= set((await session.execute(
        select(Admission.id).join(Payment, Payment.invoice_id == Admission.final_invoice_id)
        .where(Payment.received_at >= start, Payment.received_at < end)
    )).scalars())
    if not touched:
        return []

    admissions = (await session.execute(
        select(Admission, Patient).join(Patient, Patient.id == Admission.patient_id)
        .where(Admission.id.in_(touched), Admission.status != AdmissionStatus.CANCELLED)
        .order_by(Admission.ip_number)
    )).all()
    rows: List[Dict[str, Any]] = []
    for admission, patient in admissions:
        movements: List[Dict[str, Any]] = []
        for charge in (await session.execute(
            select(AdmissionCharge).where(AdmissionCharge.admission_id == admission.id,
                                          AdmissionCharge.charged_on <= date_to)
        )).scalars():
            movements.append({"on": charge.charged_on, "order": 1, "particulars": charge.description,
                              "debit_paise": charge.total_paise, "credit_paise": 0})
        admitted_on = _local_day(admission.admitted_at)
        if admission.advance_paid_paise and admitted_on <= date_to:
            movements.append({"on": admitted_on, "order": 0,
                              "particulars": "Advance recorded at admission (not receipted)",
                              "debit_paise": 0, "credit_paise": admission.advance_paid_paise})
        advance_left = 0
        for deposit in (await session.execute(
            select(WalletEntry).where(WalletEntry.admission_id == admission.id,
                                      WalletEntry.kind == WalletEntryKind.DEPOSIT, WalletEntry.created_at < end)
        )).scalars():
            advance_left += deposit.amount_paise
            movements.append({"on": _local_day(deposit.created_at), "order": 0,
                              "particulars": f"Advance receipt {deposit.receipt_number}",
                              "debit_paise": 0, "credit_paise": deposit.amount_paise})
        invoice = await session.get(Invoice, admission.final_invoice_id) if admission.final_invoice_id else None
        if invoice is not None and invoice.status is not InvoiceStatus.CANCELLED:
            billed_on = _local_day(invoice.issued_at or invoice.created_at)
            if invoice.discount_paise and billed_on <= date_to:
                movements.append({"on": billed_on, "order": 2,
                                  "particulars": f"Discount on final bill {invoice.invoice_number}",
                                  "debit_paise": 0, "credit_paise": invoice.discount_paise})
            for payment in (await session.execute(
                select(Payment).where(Payment.invoice_id == invoice.id, Payment.cancelled_at.is_(None),
                                      Payment.received_at < end)
            )).scalars():
                amount = abs(payment.amount_paise)
                # A bill settled from the advance moves money already credited
                # above; only wallet credit beyond the advances is new here.
                covered = 0
                if payment.mode is PaymentMode.WALLET and not payment.is_refund:
                    covered = min(advance_left, amount)
                    advance_left -= covered
                particulars = (f"{'Refund' if payment.is_refund else 'Payment'} {payment.receipt_number} "
                               f"({payment.mode.value})")
                if covered:
                    particulars += f" - {covered / 100:,.2f} from the advance already credited"
                movements.append({
                    "on": _local_day(payment.received_at), "order": 3,
                    "particulars": particulars,
                    "debit_paise": amount if payment.is_refund else 0,
                    "credit_paise": 0 if payment.is_refund else amount - covered,
                })
        for line in running_ledger(movements, date_from=date_from):
            rows.append({"ip_number": admission.ip_number, "patient_name": patient.name, **line})
    return rows


register(COLLECTION_SUMMARY, _collection_summary)
register(CONSULTANT_BILLING, _consultant_billing)
register(DEPARTMENT_BILLING, _department_billing)
register(PATIENT_LIST, _patient_list)
register(WALLET_REPORT, _wallet_report)
register(INPATIENT_BALANCES, _inpatient_balances)
register(INPATIENT_LEDGER, _inpatient_ledger)
