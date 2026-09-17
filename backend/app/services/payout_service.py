"""Consultant payouts: preview, approve, pay, cancel.

The arithmetic is in `app/accounts/payout.py`. Here:

* **Approving** re-computes the payout from the bills (never trusting a
  preview the screen held), locks every bill it counted so it cannot be
  amended, cancelled or counted again, and posts the fee as owed: Dr
  consultant fees, Cr that consultant's fees payable.
* **Paying** posts the payment: Dr fees payable, Cr cash or bank for what was
  handed over, Cr TDS payable for tax deducted.
* **Cancelling** is allowed only before payment. It unlocks the bills and
  reverses the fee.
"""
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import payout as rules
from app.accounts.posting import Draft, Line
from app.core.clock import day_bounds, local_today, to_local
from app.core.financial_year import label_for
from app.models.accounts import ConsultantPayout, ConsultantPayoutItem, Voucher
from app.models.consultant import Consultant
from app.models.emr import DocumentCounter, Invoice, InvoiceLine, Payment, ServiceItem
from app.models.enums import InvoiceStatus
from app.models.patient import Patient
from app.models.user import User
from app.services.accounts_service import AccountsError, AccountsService

PAY_LEDGER = {"cash": "cash", "upi": "bank_main", "net_banking": "bank_main", "cheque": "bank_main"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PayoutService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.books = AccountsService(session)

    async def _consultant(self, consultant_id: uuid.UUID) -> Consultant:
        consultant = await self.session.get(Consultant, consultant_id)
        if consultant is None:
            raise AccountsError("Consultant not found.", status_code=404)
        return consultant

    async def set_terms(self, consultant_id: uuid.UUID, *, percent: int, categories: List[str]) -> Consultant:
        consultant = await self._consultant(consultant_id)
        problem = rules.validate_terms(percent, categories)
        if problem:
            raise AccountsError(problem)
        consultant.payout_share_percent = percent
        consultant.payout_categories = [c for c in rules.CATEGORIES if c in set(categories)]
        await self.session.flush()
        return consultant

    async def _lines(self, invoice_ids: List[uuid.UUID]) -> Dict[uuid.UUID, List[Dict[str, Any]]]:
        found: Dict[uuid.UUID, List[Dict[str, Any]]] = defaultdict(list)
        if not invoice_ids:
            return found
        for line, category in (await self.session.execute(
            select(InvoiceLine, ServiceItem.category)
            .outerjoin(ServiceItem, ServiceItem.id == InvoiceLine.service_item_id)
            .where(InvoiceLine.invoice_id.in_(invoice_ids))
        )).all():
            found[line.invoice_id].append({"category": category.value if category else None,
                                           "taxable": line.taxable_paise})
        return found

    async def _candidates(
        self, consultant: Consultant, date_from: date, date_to: date, *, lock: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        start, _ = day_bounds(date_from)
        _, end = day_bounds(date_to)
        percent = consultant.payout_share_percent
        categories = consultant.payout_categories or ["consultation"]

        statement = (select(Invoice, Patient).join(Patient, Patient.id == Invoice.patient_id)
                     .where(Invoice.consultant_id == consultant.id, Invoice.issued_at >= start,
                            Invoice.issued_at < end, Invoice.status != InvoiceStatus.CANCELLED,
                            Invoice.payout_locked_at.is_(None))
                     .order_by(Invoice.issued_at))
        if lock:
            statement = statement.with_for_update(of=Invoice)
        bills = (await self.session.execute(statement)).all()
        lines = await self._lines([invoice.id for invoice, _ in bills])
        items: List[Dict[str, Any]] = []
        waiting: List[Dict[str, Any]] = []
        for invoice, patient in bills:
            eligible = rules.eligible_amount(lines[invoice.id], invoice.taxable_paise, categories)
            if eligible <= 0:
                continue
            state = rules.settlement(invoice.total_paise, invoice.paid_paise)
            common = {"invoice_id": invoice.id, "invoice_number": invoice.invoice_number,
                      "invoice_date": to_local(invoice.issued_at).date(), "patient_name": patient.name}
            if state != "settled":
                waiting.append({**common, "total_paise": invoice.total_paise, "paid_paise": invoice.paid_paise,
                                "eligible_paise": eligible, "reason": rules.WAITING_REASON.get(state, state)})
                continue
            items.append({**common, "kind": "bill", "payment_id": None, "eligible_paise": eligible,
                          "base_paise": eligible, "share_paise": rules.share(eligible, percent)})

        claimed = select(ConsultantPayoutItem.payment_id).join(
            ConsultantPayout, ConsultantPayout.id == ConsultantPayoutItem.payout_id
        ).where(ConsultantPayout.status != "cancelled", ConsultantPayoutItem.payment_id.is_not(None))
        refunds = (await self.session.execute(
            select(Payment, Invoice, Patient).join(Invoice, Invoice.id == Payment.invoice_id)
            .join(Patient, Patient.id == Invoice.patient_id)
            .where(Invoice.consultant_id == consultant.id, Invoice.payout_locked_at.is_not(None),
                   Payment.is_refund.is_(True), Payment.cancelled_at.is_(None),
                   Payment.received_at > Invoice.payout_locked_at, Payment.received_at < end,
                   Payment.id.notin_(claimed))
            .order_by(Payment.received_at)
        )).all()
        refund_lines = await self._lines([invoice.id for _, invoice, _ in refunds])
        for payment, invoice, patient in refunds:
            eligible = rules.eligible_amount(refund_lines[invoice.id], invoice.taxable_paise, categories)
            clawback = rules.refund_clawback(abs(payment.amount_paise), invoice.total_paise, eligible, percent)
            if not clawback["base_paise"]:
                continue
            items.append({"kind": "refund", "invoice_id": invoice.id, "payment_id": payment.id,
                          "invoice_number": invoice.invoice_number,
                          "invoice_date": to_local(payment.received_at).date(), "patient_name": patient.name,
                          "eligible_paise": eligible, **clawback})
        return items, waiting

    async def preview(self, consultant_id: uuid.UUID, date_from: date, date_to: date) -> Dict[str, Any]:
        consultant = await self._consultant(consultant_id)
        if date_from > date_to:
            raise AccountsError("The start date is after the end date.")
        items, waiting = await self._candidates(consultant, date_from, date_to)
        return {
            "consultant": {"id": consultant.id, "full_name": consultant.full_name,
                           "department": consultant.department.value},
            "share_percent": consultant.payout_share_percent,
            "categories": consultant.payout_categories or ["consultation"],
            "date_from": date_from, "date_to": date_to, "items": items, "waiting": waiting,
            "base_paise": sum(item["base_paise"] for item in items),
            "share_paise": sum(item["share_paise"] for item in items),
        }

    async def _next_number(self, on: date) -> str:
        year = label_for(on)
        lookup = (select(DocumentCounter)
                  .where(DocumentCounter.scope == "payout", DocumentCounter.period == year).with_for_update())
        counter = (await self.session.execute(lookup)).scalar_one_or_none()
        if counter is None:
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope="payout", period=year, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = (await self.session.execute(lookup)).scalar_one()
        counter.last_value += 1
        await self.session.flush()
        return f"CP/{year}/{counter.last_value:04d}"

    async def approve(self, consultant_id: uuid.UUID, date_from: date, date_to: date, *,
                      notes: Optional[str], user: User) -> ConsultantPayout:
        consultant = await self._consultant(consultant_id)
        today = local_today()
        if consultant.payout_share_percent <= 0:
            raise AccountsError(f"{consultant.full_name} has no payout share set.")
        if date_from > date_to:
            raise AccountsError("The start date is after the end date.")
        if date_to > today:
            raise AccountsError("A payout period cannot end in the future.")
        items, _waiting = await self._candidates(consultant, date_from, date_to, lock=True)
        if not items:
            raise AccountsError("There is nothing to pay for this consultant and period.")
        share_total = sum(item["share_paise"] for item in items)
        if share_total <= 0:
            raise AccountsError("Refunds clawed back exceed the shares earned in this period. "
                                "Include a longer period, or wait for more settled bills.")
        now = _now()
        payout = ConsultantPayout(
            payout_number=await self._next_number(today), consultant_id=consultant.id,
            consultant_name=consultant.full_name, period_from=date_from, period_to=date_to,
            share_percent=consultant.payout_share_percent,
            categories=",".join(consultant.payout_categories or ["consultation"]),
            base_paise=sum(item["base_paise"] for item in items), share_paise=share_total,
            status="approved", approved_at=now, approved_by_name=user.full_name,
            notes=(notes or "").strip() or None,
        )
        self.session.add(payout)
        await self.session.flush()
        for position, item in enumerate(items):
            self.session.add(ConsultantPayoutItem(
                payout_id=payout.id, position=position, kind=item["kind"], invoice_id=item["invoice_id"],
                payment_id=item["payment_id"], invoice_number=item["invoice_number"],
                invoice_date=item["invoice_date"], patient_name=item["patient_name"],
                eligible_paise=item["eligible_paise"], base_paise=item["base_paise"],
                share_paise=item["share_paise"],
            ))
        bill_ids = [item["invoice_id"] for item in items if item["kind"] == "bill"]
        if bill_ids:
            await self.session.execute(update(Invoice).where(Invoice.id.in_(bill_ids)).values(payout_locked_at=now))
        payable = await self.books.consultant_payable(consultant)
        voucher = await self.books.post(
            Draft("journal", today,
                  f"Consultant fees {consultant.full_name}, {date_from:%d %b %Y} to {date_to:%d %b %Y} "
                  f"({payout.payout_number})",
                  [Line("consultant_fees", debit=share_total), Line(f"ledger:{payable.id}", credit=share_total)],
                  consultant_id=consultant.id),
            source_type="payout", source_id=payout.id, created_by_name=user.full_name,
        )
        payout.accrual_voucher_id = voucher.id
        await self.session.flush()
        return payout

    async def _lock(self, payout_id: uuid.UUID) -> ConsultantPayout:
        payout = (await self.session.execute(
            select(ConsultantPayout).where(ConsultantPayout.id == payout_id).with_for_update()
        )).scalar_one_or_none()
        if payout is None:
            raise AccountsError("Payout not found.", status_code=404)
        return payout

    async def pay(self, payout_id: uuid.UUID, *, mode: str, reference: Optional[str], tds_paise: int,
                  paid_on: date, user: User) -> ConsultantPayout:
        payout = await self._lock(payout_id)
        if payout.status != "approved":
            raise AccountsError(f"This payout is {payout.status} and cannot be paid.")
        if mode not in PAY_LEDGER:
            raise AccountsError("Pay by cash, UPI, net banking or cheque.")
        if mode != "cash" and not (reference or "").strip():
            raise AccountsError("Record the transfer or cheque reference.")
        if not 0 <= tds_paise <= payout.share_paise:
            raise AccountsError("TDS must be between nothing and the whole share.")
        if paid_on > local_today() or paid_on < to_local(payout.approved_at).date():
            raise AccountsError("The payment date must be between approval and today.")
        consultant = await self._consultant(payout.consultant_id)
        payable = await self.books.consultant_payable(consultant)
        net = payout.share_paise - tds_paise
        lines = [Line(f"ledger:{payable.id}", debit=payout.share_paise)]
        if net:
            lines.append(Line(PAY_LEDGER[mode], credit=net))
        if tds_paise:
            lines.append(Line("tds_payable", credit=tds_paise))
        voucher = await self.books.post(
            Draft("payment", paid_on, f"Consultant fees paid to {payout.consultant_name} ({payout.payout_number})"
                  + (f", ref {reference.strip()}" if reference and reference.strip() else ""),
                  lines, consultant_id=payout.consultant_id),
            source_type="payout_payment", source_id=payout.id, created_by_name=user.full_name,
        )
        payout.status = "paid"
        payout.tds_paise = tds_paise
        payout.net_paid_paise = net
        payout.paid_at = _now()
        payout.paid_on = paid_on
        payout.paid_by_name = user.full_name
        payout.payment_mode = mode
        payout.payment_reference = (reference or "").strip() or None
        payout.payment_voucher_id = voucher.id
        await self.session.flush()
        return payout

    async def cancel(self, payout_id: uuid.UUID, *, reason: str, user: User) -> ConsultantPayout:
        payout = await self._lock(payout_id)
        if payout.status != "approved":
            raise AccountsError("Only a payout not yet paid can be cancelled.")
        if len((reason or "").strip()) < 3:
            raise AccountsError("Give a reason for cancelling.")
        bill_ids = [item.invoice_id for item in (await self.session.execute(
            select(ConsultantPayoutItem).where(ConsultantPayoutItem.payout_id == payout.id,
                                               ConsultantPayoutItem.kind == "bill"))).scalars()]
        if bill_ids:
            await self.session.execute(update(Invoice).where(Invoice.id.in_(bill_ids)).values(payout_locked_at=None))
        if payout.accrual_voucher_id:
            voucher = await self.session.get(Voucher, payout.accrual_voucher_id)
            if voucher is not None and voucher.status == "posted":
                await self.books.reverse(voucher, on=local_today(), reason=f"payout cancelled: {reason.strip()}",
                                         by=user.full_name)
        payout.status = "cancelled"
        payout.cancelled_at = _now()
        payout.cancelled_by_name = user.full_name
        payout.cancel_reason = reason.strip()
        await self.session.flush()
        return payout

    async def list(self, *, date_from: Optional[date] = None, date_to: Optional[date] = None,
                   consultant_id: Optional[uuid.UUID] = None) -> List[ConsultantPayout]:
        statement = select(ConsultantPayout).order_by(ConsultantPayout.approved_at.desc())
        if date_from:
            statement = statement.where(ConsultantPayout.period_to >= date_from)
        if date_to:
            statement = statement.where(ConsultantPayout.period_from <= date_to)
        if consultant_id:
            statement = statement.where(ConsultantPayout.consultant_id == consultant_id)
        return list((await self.session.execute(statement)).scalars())

    async def get(self, payout_id: uuid.UUID) -> Tuple[ConsultantPayout, List[ConsultantPayoutItem]]:
        payout = await self.session.get(ConsultantPayout, payout_id)
        if payout is None:
            raise AccountsError("Payout not found.", status_code=404)
        items = list((await self.session.execute(
            select(ConsultantPayoutItem).where(ConsultantPayoutItem.payout_id == payout.id)
            .order_by(ConsultantPayoutItem.position))).scalars())
        return payout, items
