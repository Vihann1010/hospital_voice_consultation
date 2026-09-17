"""The six reports the front office runs.

Cash ledger, day-wise receipts and refunds, invoice list, services billing,
refund list, daily closing. Between them they answer every question asked at
the end of an OPD day.

Two rules run through all of them.

**Cancelled things are excluded from money and kept in lists.** A cancelled
bill contributes nothing to any total — but it still appears in the invoice
list, because somebody holding that bill needs to find it. A cancelled
receipt disappears from the cash ledger entirely: it records money that never
moved, and a till that lists it cannot be counted against the drawer.

**Wallet money is counted once, where it arrives.** A deposit is a collection
on the day it is taken; spending it later against a bill is not. This is the
same rule the collections summary follows, and the reports have to agree with
it or the day will not close.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import day_bounds, to_local
from app.models.emr import (
    CashSession,
    Invoice,
    InvoiceLine,
    Payment,
    ServiceItem,
    Visit,
    WalletEntry,
)
from app.models.enums import (
    CashSessionStatus,
    InvoiceStatus,
    PaymentMode,
    WalletEntryKind,
)
from app.models.patient import Patient
from app.reports.definitions import Column, ColumnType, ReportSpec, register
from app.reports.sources import invoice_sources

M = ColumnType.MONEY
T = ColumnType.TEXT
N = ColumnType.NUMBER


def _window(date_from: date, date_to: date):
    """UTC bounds covering the hospital's local days, inclusive."""
    start, _ = day_bounds(date_from)
    _, end = day_bounds(date_to)
    return start, end


# ------------------------------------------------------------- cash ledger
CASH_LEDGER = ReportSpec(
    key="cash-ledger",
    title="Cash ledger",
    description="Every movement through the till, in order.",
    self_service=True,
    columns=[
        Column("at", "Time", ColumnType.DATETIME),
        Column("receipt_number", "Receipt"),
        Column("patient_name", "Patient"),
        Column("uhid", "UHID", default_visible=False),
        Column("particulars", "Particulars"),
        Column("mode", "Mode", ColumnType.STATUS),
        Column("instrument", "Instrument", default_visible=False),
        Column("in_paise", "In", M, total=True),
        Column("out_paise", "Out", M, total=True),
        Column("received_by", "By"),
    ],
)


async def _cash_ledger(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    user_name: Optional[str] = None,
    **_: Any,
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)
    rows: List[Dict[str, Any]] = []

    conditions = [
        Payment.received_at >= start,
        Payment.received_at < end,
        # A struck receipt records money that never moved. Listing it would
        # make the ledger impossible to count against the drawer.
        Payment.cancelled_at.is_(None),
        # Credit spent against a bill is not cash arriving; it was banked on
        # the day it was deposited, and the deposit is listed below.
        Payment.mode != PaymentMode.WALLET,
        # Nor is an insurer's share put on the bill; that money arrives later
        # as a claim settlement, and never through a drawer.
        Payment.mode != PaymentMode.INSURANCE,
    ]
    if user_name:
        conditions.append(Payment.received_by_name == user_name)

    result = await session.execute(
        select(Payment, Invoice, Patient)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(Patient, Patient.id == Invoice.patient_id)
        .where(*conditions)
    )
    for payment, invoice, patient in result.all():
        incoming = not payment.is_refund
        amount = abs(payment.amount_paise)
        instrument = ""
        if payment.mode_details:
            instrument = ", ".join(
                str(value) for value in payment.mode_details.values() if value
            )
        rows.append({
            "at": to_local(payment.received_at),
            "receipt_number": payment.receipt_number,
            "patient_name": patient.name,
            "uhid": patient.uhid or "",
            "particulars": (
                f"{'Payment' if incoming else 'Refund'} · {invoice.invoice_number}"
            ),
            "mode": payment.mode.value,
            "instrument": instrument,
            "in_paise": amount if incoming else 0,
            "out_paise": 0 if incoming else amount,
            "received_by": payment.received_by_name,
        })

    wallet_conditions = [
        WalletEntry.created_at >= start,
        WalletEntry.created_at < end,
        WalletEntry.kind.in_((WalletEntryKind.DEPOSIT, WalletEntryKind.WITHDRAWAL)),
    ]
    if user_name:
        wallet_conditions.append(WalletEntry.created_by_name == user_name)

    result = await session.execute(
        select(WalletEntry, Patient)
        .join(Patient, Patient.id == WalletEntry.patient_id)
        .where(*wallet_conditions)
    )
    for entry, patient in result.all():
        incoming = entry.amount_paise > 0
        rows.append({
            "at": to_local(entry.created_at),
            "receipt_number": entry.receipt_number or "",
            "patient_name": patient.name,
            "uhid": patient.uhid or "",
            "particulars": "Advance received" if incoming else "Advance returned",
            "mode": entry.mode.value if entry.mode else "cash",
            "instrument": entry.reason or "",
            "in_paise": entry.amount_paise if incoming else 0,
            "out_paise": 0 if incoming else abs(entry.amount_paise),
            "received_by": entry.created_by_name,
        })

    rows.sort(key=lambda row: row["at"])
    return rows


# --------------------------------------------------- receipts and refunds
DAY_WISE = ReportSpec(
    key="receipts-and-refunds",
    title="Day-wise receipts and refunds",
    description="What came in and what went back out, day by day.",
    columns=[
        Column("day", "Date", ColumnType.DATE),
        Column("receipt_count", "Receipts", N, total=True),
        Column("received_paise", "Collected", M, total=True),
        Column("refund_count", "Refunds", N, total=True),
        Column("refunded_paise", "Refunded", M, total=True),
        Column("net_paise", "Net", M, total=True),
    ],
)


async def _day_wise(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)

    # Bucketed in Python rather than by a SQL date_trunc, because the day
    # that matters is the hospital's and the column is UTC. Grouping in the
    # database would file everything before 05:30 IST under the day before.
    buckets: Dict[date, Dict[str, int]] = {}

    def bucket(day: date) -> Dict[str, int]:
        return buckets.setdefault(
            day,
            {"receipt_count": 0, "received_paise": 0,
             "refund_count": 0, "refunded_paise": 0},
        )

    result = await session.execute(
        select(Payment).where(
            Payment.received_at >= start,
            Payment.received_at < end,
            Payment.cancelled_at.is_(None),
            Payment.mode != PaymentMode.WALLET,
            Payment.mode != PaymentMode.INSURANCE,
        )
    )
    for payment in result.scalars():
        row = bucket(to_local(payment.received_at).date())
        if payment.is_refund:
            row["refund_count"] += 1
            row["refunded_paise"] += abs(payment.amount_paise)
        else:
            row["receipt_count"] += 1
            row["received_paise"] += payment.amount_paise

    result = await session.execute(
        select(WalletEntry).where(
            WalletEntry.created_at >= start,
            WalletEntry.created_at < end,
            WalletEntry.kind.in_((WalletEntryKind.DEPOSIT, WalletEntryKind.WITHDRAWAL)),
        )
    )
    for entry in result.scalars():
        row = bucket(to_local(entry.created_at).date())
        if entry.amount_paise > 0:
            row["receipt_count"] += 1
            row["received_paise"] += entry.amount_paise
        else:
            row["refund_count"] += 1
            row["refunded_paise"] += abs(entry.amount_paise)

    rows = []
    # Every day in the range, including the empty ones. A gap in a day-wise
    # report reads as "no data was recorded", which is a different and much
    # more alarming thing than "nobody came in".
    day = date_from
    while day <= date_to:
        found = buckets.get(day, {"receipt_count": 0, "received_paise": 0,
                                  "refund_count": 0, "refunded_paise": 0})
        rows.append({
            "day": day,
            **found,
            "net_paise": found["received_paise"] - found["refunded_paise"],
        })
        day += timedelta(days=1)
    rows.reverse()
    return rows


# ------------------------------------------------------------ invoice list
INVOICE_LIST = ReportSpec(
    key="invoice-list",
    title="Invoice list",
    description="Every bill raised, with what is still owed on it.",
    columns=[
        Column("issued_on", "Date", ColumnType.DATE),
        Column("invoice_number", "Bill"),
        Column("patient_name", "Patient"),
        Column("uhid", "UHID"),
        Column("doctor_name", "Consultant"),
        Column("source", "From"),
        Column("visit_number", "Visit", default_visible=False),
        Column("gross_paise", "Gross", M, total=True),
        Column("discount_paise", "Discount", M, total=True),
        Column("net_paise", "Net", M, total=True),
        Column("paid_paise", "Paid", M, total=True),
        Column("balance_paise", "Balance", M, total=True),
        Column("status", "Status", ColumnType.STATUS),
    ],
)


async def _invoice_list(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)
    result = await session.execute(
        select(Invoice, Patient, Visit)
        .join(Patient, Patient.id == Invoice.patient_id)
        .outerjoin(Visit, Visit.id == Invoice.visit_id)
        .where(Invoice.created_at >= start, Invoice.created_at < end)
        .order_by(Invoice.created_at.desc())
    )

    found = result.all()
    sources = await invoice_sources(session, [invoice for invoice, _, _ in found])
    rows = []
    for invoice, patient, visit in found:
        cancelled = invoice.status is InvoiceStatus.CANCELLED
        rows.append({
            "issued_on": to_local(invoice.issued_at or invoice.created_at).date(),
            "invoice_number": invoice.invoice_number,
            "patient_name": patient.name,
            "uhid": patient.uhid or "",
            "doctor_name": invoice.doctor_name or (visit.doctor_name if visit else ""),
            "source": sources.get(invoice.id, ""),
            "visit_number": visit.visit_number if visit else "",
            # A cancelled bill stays in the list and out of every total.
            "gross_paise": 0 if cancelled else invoice.gross_paise,
            "discount_paise": 0 if cancelled else invoice.discount_paise,
            "net_paise": 0 if cancelled else invoice.total_paise,
            "paid_paise": 0 if cancelled else invoice.paid_paise,
            "balance_paise": (
                0 if cancelled else invoice.total_paise - invoice.paid_paise
            ),
            "status": invoice.status.value,
        })
    return rows


# --------------------------------------------------------- services billing
SERVICES = ReportSpec(
    key="services-billing",
    title="Services billing",
    description="What was charged for, and how much of it.",
    columns=[
        Column("code", "Code"),
        Column("name", "Service"),
        Column("category", "Category", ColumnType.STATUS),
        Column("quantity", "Qty", N, total=True),
        Column("gross_paise", "Gross", M, total=True),
        Column("discount_paise", "Discount", M, total=True),
        Column("net_paise", "Net", M, total=True),
    ],
)


async def _services(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)
    result = await session.execute(
        select(
            InvoiceLine.code,
            InvoiceLine.description,
            ServiceItem.category,
            func.sum(InvoiceLine.quantity),
            func.sum(InvoiceLine.unit_rate_paise * InvoiceLine.quantity),
            func.sum(InvoiceLine.discount_paise),
            func.sum(InvoiceLine.total_paise),
        )
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .outerjoin(ServiceItem, ServiceItem.id == InvoiceLine.service_item_id)
        .where(
            Invoice.created_at >= start,
            Invoice.created_at < end,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
        .group_by(InvoiceLine.code, InvoiceLine.description, ServiceItem.category)
        .order_by(func.sum(InvoiceLine.total_paise).desc())
    )

    return [
        {
            "code": code or "",
            "name": description,
            "category": category.value if category else "",
            "quantity": int(quantity or 0),
            "gross_paise": int(gross or 0),
            "discount_paise": int(discount or 0),
            "net_paise": int(net or 0),
        }
        for code, description, category, quantity, gross, discount, net in result.all()
    ]


# --------------------------------------------------------------- refund list
REFUNDS = ReportSpec(
    key="refund-list",
    title="Refund list",
    description="Every rupee returned, and why.",
    columns=[
        Column("at", "When", ColumnType.DATETIME),
        Column("receipt_number", "Voucher"),
        Column("patient_name", "Patient"),
        Column("uhid", "UHID", default_visible=False),
        Column("against", "Against"),
        Column("source", "From"),
        Column("mode", "Mode", ColumnType.STATUS),
        Column("amount_paise", "Amount", M, total=True),
        Column("reason", "Reason"),
        Column("issued_by", "Issued by"),
    ],
)


async def _refunds(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, end = _window(date_from, date_to)
    rows: List[Dict[str, Any]] = []

    result = await session.execute(
        select(Payment, Invoice, Patient)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(Patient, Patient.id == Invoice.patient_id)
        .where(
            Payment.received_at >= start,
            Payment.received_at < end,
            Payment.is_refund.is_(True),
            Payment.cancelled_at.is_(None),
        )
    )
    found = result.all()
    sources = await invoice_sources(session, [invoice for _, invoice, _ in found])
    for payment, invoice, patient in found:
        rows.append({
            "at": to_local(payment.received_at),
            "receipt_number": payment.receipt_number,
            "patient_name": patient.name,
            "uhid": patient.uhid or "",
            "against": invoice.invoice_number,
            "source": sources.get(invoice.id, ""),
            # A refund credited to the wallet is listed as such: the money
            # did not leave the building, and a report that showed it as cash
            # out would not reconcile against the drawer.
            "mode": payment.mode.value,
            "amount_paise": abs(payment.amount_paise),
            "reason": payment.refund_reason or "",
            "issued_by": payment.received_by_name,
        })

    result = await session.execute(
        select(WalletEntry, Patient)
        .join(Patient, Patient.id == WalletEntry.patient_id)
        .where(
            WalletEntry.created_at >= start,
            WalletEntry.created_at < end,
            WalletEntry.kind == WalletEntryKind.WITHDRAWAL,
        )
    )
    for entry, patient in result.all():
        rows.append({
            "at": to_local(entry.created_at),
            "receipt_number": entry.receipt_number or "",
            "patient_name": patient.name,
            "uhid": patient.uhid or "",
            "against": "Advance on account",
            "source": "Wallet",
            "mode": entry.mode.value if entry.mode else "cash",
            "amount_paise": abs(entry.amount_paise),
            "reason": entry.reason or "",
            "issued_by": entry.created_by_name,
        })

    rows.sort(key=lambda row: row["at"], reverse=True)
    return rows


# ------------------------------------------------------------ daily closing
DAILY_CLOSING = ReportSpec(
    key="daily-closing",
    title="Daily closing",
    description="What each cashier should be handing over.",
    single_day=True,
    self_service=True,
    columns=[
        Column("cashier", "Cashier"),
        Column("counter", "Counter", default_visible=False),
        Column("opening_float_paise", "Opening float", M, total=True),
        Column("cash_paise", "Cash in", M, total=True),
        Column("cash_out_paise", "Cash out", M, total=True),
        Column("expected_cash_paise", "Expected in drawer", M, total=True),
        Column("counted_cash_paise", "Counted", M, total=True),
        Column("variance_paise", "Over / short", M, total=True),
        Column("other_modes_paise", "Card, UPI, other", M, total=True),
        Column("status", "Shift", ColumnType.STATUS),
    ],
)


async def _daily_closing(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    user_name: Optional[str] = None,
    **_: Any,
) -> List[Dict[str, Any]]:
    """One line per cashier, showing what should be in their drawer.

    Cash is separated from every other mode on purpose: a card settlement
    reaches the bank on its own and is not in anybody's drawer, so folding it
    into the expected figure would make every shift look short.
    """
    start, end = _window(date_from, date_to)

    tills: Dict[str, Dict[str, Any]] = {}

    def till(name: str) -> Dict[str, Any]:
        return tills.setdefault(name, {
            "cashier": name or "—",
            "counter": "",
            "opening_float_paise": 0,
            "cash_paise": 0,
            "cash_out_paise": 0,
            "other_modes_paise": 0,
            "counted_cash_paise": 0,
            "variance_paise": 0,
            "status": "open",
        })

    sessions = await session.execute(
        select(CashSession).where(
            CashSession.opened_at >= start, CashSession.opened_at < end
        )
    )
    for shift in sessions.scalars():
        if user_name and shift.cashier_name != user_name:
            continue
        row = till(shift.cashier_name)
        row["counter"] = shift.counter_name
        row["opening_float_paise"] += shift.opening_float_paise
        row["counted_cash_paise"] += shift.counted_cash_paise or 0
        row["status"] = shift.status.value
        if shift.status is not CashSessionStatus.OPEN:
            row["variance_paise"] += shift.variance_paise or 0

    payments = await session.execute(
        select(Payment).where(
            Payment.received_at >= start,
            Payment.received_at < end,
            Payment.cancelled_at.is_(None),
            Payment.mode != PaymentMode.WALLET,
        )
    )
    for payment in payments.scalars():
        if user_name and payment.received_by_name != user_name:
            continue
        row = till(payment.received_by_name)
        amount = abs(payment.amount_paise)
        if payment.mode is PaymentMode.INSURANCE:
            # The insurer's share on a bill: no money at any counter.
            continue
        if payment.mode is PaymentMode.CASH:
            key = "cash_out_paise" if payment.is_refund else "cash_paise"
            row[key] += amount
        elif not payment.is_refund:
            row["other_modes_paise"] += amount
        else:
            row["other_modes_paise"] -= amount

    wallet = await session.execute(
        select(WalletEntry).where(
            WalletEntry.created_at >= start,
            WalletEntry.created_at < end,
            WalletEntry.kind.in_((WalletEntryKind.DEPOSIT, WalletEntryKind.WITHDRAWAL)),
        )
    )
    for entry in wallet.scalars():
        if user_name and entry.created_by_name != user_name:
            continue
        row = till(entry.created_by_name)
        # Only cash reaches the drawer; an advance paid by card or UPI is
        # counted with the other modes.
        if entry.mode not in (None, PaymentMode.CASH):
            row["other_modes_paise"] += entry.amount_paise
        elif entry.amount_paise > 0:
            row["cash_paise"] += entry.amount_paise
        else:
            row["cash_out_paise"] += abs(entry.amount_paise)

    rows = []
    for row in tills.values():
        row["expected_cash_paise"] = (
            row["opening_float_paise"] + row["cash_paise"] - row["cash_out_paise"]
        )
        rows.append(row)
    rows.sort(key=lambda item: item["cashier"])
    return rows


register(CASH_LEDGER, _cash_ledger)
register(DAY_WISE, _day_wise)
register(INVOICE_LIST, _invoice_list)
register(SERVICES, _services)
register(REFUNDS, _refunds)
register(DAILY_CLOSING, _daily_closing)
