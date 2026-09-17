"""The books: chart of accounts, vouchers, balances, and posting from the counter.

The posting rules — what each bill, receipt and advance means — are in
`app/accounts/posting.py`. This service loads the records, keeps the chart,
numbers and writes vouchers, and keeps each source record's voucher in step
with the record:

* a record never posted is posted, dated when it happened;
* a record whose voucher still says the same thing is left alone;
* a record that has changed (a bill amended, a receipt cancelled) has its
  voucher reversed on the day of the change, and — if there is still anything
  to post — a replacement posted beside the reversal.

Voucher numbers are gapless within a financial year and voucher type, from
the shared document counter, like invoices and receipts.
"""
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import chart, posting
from app.core.clock import local_today, to_local
from app.core.financial_year import label_for
from app.models.accounts import AccountGroup, Ledger, Voucher, VoucherLine
from app.models.consultant import Consultant
from app.models.emr import (
    DocumentCounter, InsuranceClaim, Invoice, InvoiceLine, Payment, ServiceItem, WalletEntry,
)
from app.models.insurance import ClaimSettlement
from app.models.enums import InvoiceStatus
from app.models.ipd import Admission
from app.models.patient import Patient
from app.reports.sources import invoice_sources

VOUCHER_PREFIX = {"sales": "SL", "receipt": "RC", "payment": "PY", "journal": "JV", "contra": "CT"}
MANUAL_TYPES = ("journal", "payment", "receipt", "contra")
CHART_LOCK = 72_417_003


class AccountsError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(moment: Optional[datetime]) -> Optional[date]:
    return to_local(moment).date() if moment else None


class AccountsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._ledgers: Dict[str, Ledger] = {}

    # ================================================================ chart
    async def ensure_chart(self) -> Dict[str, Ledger]:
        """Create any missing system group or ledger. Safe to call on every request."""
        if self._ledgers:
            return self._ledgers
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CHART_LOCK})
        groups = {group.code: group for group in (await self.session.execute(select(AccountGroup))).scalars()}
        for position, (code, name, nature, parent) in enumerate(chart.GROUPS):
            if code not in groups:
                group = AccountGroup(code=code, name=name, nature=nature, is_system=True, position=position,
                                     parent_id=groups[parent].id if parent else None)
                self.session.add(group)
                await self.session.flush()
                groups[code] = group
        ledgers = {ledger.system_key: ledger for ledger in (await self.session.execute(
            select(Ledger).where(Ledger.system_key.is_not(None)))).scalars()}
        for key, code, name, group_code in chart.LEDGERS:
            if key not in ledgers:
                ledger = Ledger(code=code, name=name, group_id=groups[group_code].id, system_key=key, is_system=True)
                self.session.add(ledger)
                await self.session.flush()
                ledgers[key] = ledger
        self._ledgers = ledgers
        return ledgers

    async def resolve(self, key: str) -> Ledger:
        if key.startswith("ledger:"):
            ledger = await self.session.get(Ledger, uuid.UUID(key[len("ledger:"):]))
        else:
            ledger = (await self.ensure_chart()).get(key)
        if ledger is None:
            raise AccountsError(f"There is no ledger {key}.")
        if not ledger.is_active:
            raise AccountsError(f"{ledger.name} is closed to new entries.")
        return ledger

    async def consultant_payable(self, consultant: Consultant) -> Ledger:
        found = (await self.session.execute(
            select(Ledger).where(Ledger.consultant_id == consultant.id))).scalar_one_or_none()
        if found is not None:
            return found
        await self.ensure_chart()
        group = (await self.session.execute(
            select(AccountGroup).where(AccountGroup.code == "CONS_PAYABLE"))).scalar_one()
        ledger = Ledger(code=f"L-CP-{consultant.id.hex[:8].upper()}",
                        name=f"{consultant.full_name} - fees payable", group_id=group.id,
                        consultant_id=consultant.id, is_system=True)
        self.session.add(ledger)
        await self.session.flush()
        return ledger

    # ============================================================ vouchers
    async def _next_number(self, voucher_type: str, on: date) -> Tuple[str, str]:
        year = label_for(on)
        scope = f"voucher-{voucher_type}"
        lookup = (select(DocumentCounter)
                  .where(DocumentCounter.scope == scope, DocumentCounter.period == year).with_for_update())
        counter = (await self.session.execute(lookup)).scalar_one_or_none()
        if counter is None:
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope=scope, period=year, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = (await self.session.execute(lookup)).scalar_one()
        counter.last_value += 1
        await self.session.flush()
        return f"{VOUCHER_PREFIX[voucher_type]}/{year}/{counter.last_value:05d}", year

    async def post(
        self, draft: posting.Draft, *, source_type: Optional[str] = None, source_id: Optional[uuid.UUID] = None,
        created_by_name: str = "Books posting", is_manual: bool = False,
    ) -> Voucher:
        if draft.voucher_type not in VOUCHER_PREFIX:
            raise AccountsError(f"{draft.voucher_type} is not a voucher type.")
        try:
            posting.check_balanced(draft.lines)
        except posting.PostingError as exc:
            raise AccountsError(str(exc)) from exc
        resolved = [(await self.resolve(line.ledger), line) for line in draft.lines]
        number, year = await self._next_number(draft.voucher_type, draft.on)
        voucher = Voucher(
            voucher_number=number, voucher_type=draft.voucher_type, financial_year=year,
            voucher_date=draft.on, narration=draft.narration[:2000], source_type=source_type,
            source_id=source_id, fingerprint=draft.fingerprint(), status="posted",
            patient_id=draft.patient_id, consultant_id=draft.consultant_id, is_manual=is_manual,
            created_by_name=created_by_name,
        )
        self.session.add(voucher)
        await self.session.flush()
        for position, (ledger, line) in enumerate(resolved):
            self.session.add(VoucherLine(voucher_id=voucher.id, position=position, ledger_id=ledger.id,
                                         debit_paise=line.debit, credit_paise=line.credit,
                                         narration=line.narration))
        await self.session.flush()
        return voucher

    async def reverse(self, voucher: Voucher, *, on: date, reason: str, by: str) -> Voucher:
        if voucher.status != "posted" or voucher.reversal_of_id is not None:
            raise AccountsError("This voucher has already been reversed, or is itself a reversal.")
        on = max(on, voucher.voucher_date)
        lines = list((await self.session.execute(
            select(VoucherLine).where(VoucherLine.voucher_id == voucher.id).order_by(VoucherLine.position)
        )).scalars())
        voucher.status = "reversed"
        voucher.reversed_at = _now()
        voucher.reversed_by_name = by
        voucher.reversal_reason = reason
        await self.session.flush()
        number, year = await self._next_number(voucher.voucher_type, on)
        reversal = Voucher(
            voucher_number=number, voucher_type=voucher.voucher_type, financial_year=year, voucher_date=on,
            narration=f"Reversal of {voucher.voucher_number}: {reason}"[:2000], source_type=voucher.source_type,
            source_id=voucher.source_id, fingerprint="reversal", status="posted", reversal_of_id=voucher.id,
            patient_id=voucher.patient_id, consultant_id=voucher.consultant_id, is_manual=voucher.is_manual,
            created_by_name=by,
        )
        self.session.add(reversal)
        await self.session.flush()
        for line in lines:
            self.session.add(VoucherLine(voucher_id=reversal.id, position=line.position, ledger_id=line.ledger_id,
                                         debit_paise=line.credit_paise, credit_paise=line.debit_paise,
                                         narration=line.narration))
        await self.session.flush()
        return reversal

    async def live_voucher(self, source_type: str, source_id: uuid.UUID) -> Optional[Voucher]:
        return (await self.session.execute(
            select(Voucher).where(Voucher.source_type == source_type, Voucher.source_id == source_id,
                                  Voucher.status == "posted", Voucher.reversal_of_id.is_(None))
        )).scalar_one_or_none()

    async def sync_source(
        self, source_type: str, source_id: uuid.UUID, draft: Optional[posting.Draft], *, change_on: date,
    ) -> str:
        live = await self.live_voucher(source_type, source_id)
        if live is None:
            if draft is None:
                return "nothing"
            await self.post(draft, source_type=source_type, source_id=source_id)
            return "posted"
        if draft is not None and live.fingerprint == draft.fingerprint():
            return "unchanged"
        await self.reverse(live, on=change_on,
                           reason="its record was cancelled" if draft is None else "its record changed",
                           by="Books posting")
        if draft is None:
            return "reversed"
        draft.on = max(change_on, live.voucher_date)
        await self.post(draft, source_type=source_type, source_id=source_id)
        return "replaced"

    # ============================================================= engine
    async def _sync_one(self, source_type, source_id, build: Callable[[], Optional[posting.Draft]],
                        change_on: date, label: str, counts: Dict[str, int], exceptions: List[Dict[str, str]]):
        try:
            async with self.session.begin_nested():
                outcome = await self.sync_source(source_type, source_id, build(), change_on=change_on)
            counts[outcome] += 1
        except (posting.PostingError, AccountsError) as exc:
            counts["failed"] += 1
            exceptions.append({"source": label, "error": str(exc)})

    async def run_posting(self, *, since: Optional[datetime] = None) -> Dict[str, Any]:
        """Bring the books up to date with the counter's records."""
        await self.ensure_chart()
        counts: Dict[str, int] = defaultdict(int)
        exceptions: List[Dict[str, str]] = []
        now = _now()
        today = local_today()

        # --- bills
        statement = select(Invoice, Patient).join(Patient, Patient.id == Invoice.patient_id)
        if since is not None:
            statement = statement.where(Invoice.updated_at >= since)
        invoices = (await self.session.execute(statement.order_by(Invoice.created_at))).all()
        sources = await invoice_sources(self.session, [invoice for invoice, _ in invoices])
        lines: Dict[uuid.UUID, List[Dict[str, Any]]] = defaultdict(list)
        if invoices:
            for line, category in (await self.session.execute(
                select(InvoiceLine, ServiceItem.category)
                .outerjoin(ServiceItem, ServiceItem.id == InvoiceLine.service_item_id)
                .where(InvoiceLine.invoice_id.in_([invoice.id for invoice, _ in invoices]))
            )).all():
                lines[line.invoice_id].append({"category": category.value if category else None,
                                               "gross": line.unit_rate_paise * line.quantity})
        for invoice, patient in invoices:
            data = {
                "number": invoice.invoice_number, "status": invoice.status.value,
                "issued_on": _day(invoice.issued_at), "gross": invoice.gross_paise,
                "discount": invoice.discount_paise,
                "tax": invoice.cgst_paise + invoice.sgst_paise + invoice.igst_paise,
                "total": invoice.total_paise, "source": sources.get(invoice.id), "lines": lines[invoice.id],
                "patient_id": patient.id, "patient_name": patient.name, "consultant_id": invoice.consultant_id,
            }
            await self._sync_one("invoice", invoice.id, lambda data=data: posting.invoice_draft(data),
                                 _day(invoice.cancelled_at or invoice.amended_at or now) or today,
                                 f"Bill {invoice.invoice_number}", counts, exceptions)

        # --- receipts and refunds
        statement = (select(Payment, Invoice, Patient).join(Invoice, Invoice.id == Payment.invoice_id)
                     .join(Patient, Patient.id == Invoice.patient_id))
        if since is not None:
            statement = statement.where(Payment.updated_at >= since)
        for payment, invoice, patient in (await self.session.execute(statement.order_by(Payment.received_at))).all():
            data = {
                "receipt_number": payment.receipt_number, "invoice_number": invoice.invoice_number,
                "mode": payment.mode.value, "is_refund": payment.is_refund, "amount": payment.amount_paise,
                "cancelled": payment.cancelled_at is not None, "on": _day(payment.received_at),
                "patient_id": patient.id, "patient_name": patient.name,
            }
            await self._sync_one("payment", payment.id, lambda data=data: posting.payment_draft(data),
                                 _day(payment.cancelled_at or now) or today,
                                 f"Receipt {payment.receipt_number}", counts, exceptions)

        # --- advances
        statement = (select(WalletEntry, Patient, Payment)
                     .join(Patient, Patient.id == WalletEntry.patient_id)
                     .outerjoin(Payment, Payment.id == WalletEntry.payment_id))
        if since is not None:
            statement = statement.where(WalletEntry.updated_at >= since)
        for entry, patient, linked in (await self.session.execute(statement.order_by(WalletEntry.created_at))).all():
            data = {
                "kind": entry.kind.value, "amount": entry.amount_paise,
                "mode": entry.mode.value if entry.mode else None, "receipt_number": entry.receipt_number,
                "payment_linked": entry.payment_id is not None,
                # What a correct reversal of a cancelled wallet receipt puts back.
                "linked_amount": linked.amount_paise if linked is not None and linked.cancelled_at else 0,
                "on": _day(entry.created_at),
                "patient_id": patient.id, "patient_name": patient.name,
            }
            await self._sync_one("wallet_entry", entry.id, lambda data=data: posting.wallet_draft(data),
                                 today, f"Advance entry {entry.receipt_number or entry.id}", counts, exceptions)

        # --- what TPAs and insurers paid against claims
        statement = (select(ClaimSettlement, InsuranceClaim, Patient)
                     .join(InsuranceClaim, InsuranceClaim.id == ClaimSettlement.claim_id)
                     .join(Patient, Patient.id == InsuranceClaim.patient_id))
        if since is not None:
            statement = statement.where(ClaimSettlement.updated_at >= since)
        for settlement, claim, patient in (await self.session.execute(
                statement.order_by(ClaimSettlement.created_at))).all():
            data = {
                "claim_number": claim.claim_number, "payer_name": claim.payer_name,
                "received": settlement.received_paise, "tds": settlement.tds_paise,
                "deduction": settlement.deduction_paise, "mode": settlement.mode,
                "cancelled": settlement.cancelled_at is not None, "on": settlement.received_on,
                "patient_id": patient.id, "patient_name": patient.name,
            }
            await self._sync_one("claim_settlement", settlement.id,
                                 lambda data=data: posting.settlement_draft(data),
                                 _day(settlement.cancelled_at or now) or today,
                                 f"Claim {claim.claim_number} settlement", counts, exceptions)

        # --- advances typed on an admission before receipts existed
        statement = (select(Admission, Invoice).join(Invoice, Invoice.id == Admission.final_invoice_id)
                     .where(Admission.advance_paid_paise > 0))
        if since is not None:
            statement = statement.where((Invoice.updated_at >= since) | (Admission.updated_at >= since))
        for admission, invoice in (await self.session.execute(statement)).all():
            data = {
                "ip_number": admission.ip_number, "invoice_number": invoice.invoice_number,
                "amount": min(admission.advance_paid_paise, invoice.total_paise),
                "invoice_cancelled": invoice.status is InvoiceStatus.CANCELLED,
                "on": _day(invoice.issued_at or invoice.created_at), "patient_id": admission.patient_id,
            }
            await self._sync_one("legacy_advance", admission.id, lambda data=data: posting.legacy_advance_draft(data),
                                 today, f"Admission {admission.ip_number} advance", counts, exceptions)

        return {**{key: counts.get(key, 0) for key in ("posted", "replaced", "reversed", "unchanged", "nothing",
                                                        "failed")},
                "exceptions": exceptions[:50], "full": since is None}

    # ============================================================ reading
    async def groups(self) -> List[AccountGroup]:
        await self.ensure_chart()
        return list((await self.session.execute(
            select(AccountGroup).order_by(AccountGroup.position, AccountGroup.name))).scalars())

    def _group_paths(self, groups: List[AccountGroup]) -> Dict[uuid.UUID, str]:
        by_id = {group.id: group for group in groups}
        paths: Dict[uuid.UUID, str] = {}
        for group in groups:
            names, cursor = [], group
            while cursor is not None:
                names.append(cursor.name)
                cursor = by_id.get(cursor.parent_id) if cursor.parent_id else None
            paths[group.id] = " / ".join(reversed(names))
        return paths

    async def _movements(self, *, date_from: Optional[date] = None,
                         date_to: Optional[date] = None) -> Dict[uuid.UUID, Tuple[int, int]]:
        statement = (select(VoucherLine.ledger_id, func.coalesce(func.sum(VoucherLine.debit_paise), 0),
                            func.coalesce(func.sum(VoucherLine.credit_paise), 0))
                     .join(Voucher, Voucher.id == VoucherLine.voucher_id).group_by(VoucherLine.ledger_id))
        if date_from is not None:
            statement = statement.where(Voucher.voucher_date >= date_from)
        if date_to is not None:
            statement = statement.where(Voucher.voucher_date <= date_to)
        return {ledger_id: (int(debit), int(credit))
                for ledger_id, debit, credit in (await self.session.execute(statement)).all()}

    async def ledgers(self, *, as_of: Optional[date] = None) -> List[Dict[str, Any]]:
        groups = await self.groups()
        paths = self._group_paths(groups)
        natures = {group.id: group.nature for group in groups}
        names = {group.id: group.name for group in groups}
        moved = await self._movements(date_to=as_of)
        rows = []
        for ledger in (await self.session.execute(select(Ledger).order_by(Ledger.name))).scalars():
            debit, credit = moved.get(ledger.id, (0, 0))
            rows.append({
                "id": ledger.id, "code": ledger.code, "name": ledger.name, "group_id": ledger.group_id,
                "group_name": names.get(ledger.group_id, ""), "group_path": paths.get(ledger.group_id, ""),
                "nature": natures.get(ledger.group_id, ""), "system_key": ledger.system_key,
                "consultant_id": ledger.consultant_id, "opening_balance_paise": ledger.opening_balance_paise,
                "balance_paise": ledger.opening_balance_paise + debit - credit,
                "is_active": ledger.is_active, "is_system": ledger.is_system, "notes": ledger.notes,
            })
        rows.sort(key=lambda row: (row["group_path"], row["name"]))
        return rows

    async def trial_balance(self, date_from: date, date_to: date) -> Dict[str, Any]:
        if date_from > date_to:
            raise AccountsError("The start date is after the end date.")
        ledgers = await self.ledgers()
        before = await self._movements(date_to=date_from - timedelta(days=1))
        within = await self._movements(date_from=date_from, date_to=date_to)
        rows = []
        for ledger in ledgers:
            b_debit, b_credit = before.get(ledger["id"], (0, 0))
            debit, credit = within.get(ledger["id"], (0, 0))
            opening = ledger["opening_balance_paise"] + b_debit - b_credit
            closing = opening + debit - credit
            if not (opening or debit or credit):
                continue
            rows.append({"ledger_id": ledger["id"], "code": ledger["code"], "name": ledger["name"],
                         "group_name": ledger["group_name"], "group_path": ledger["group_path"],
                         "nature": ledger["nature"], "opening_paise": opening, "debit_paise": debit,
                         "credit_paise": credit, "closing_paise": closing})
        totals = {key: sum(row[key] for row in rows)
                  for key in ("opening_paise", "debit_paise", "credit_paise", "closing_paise")}
        opening_difference = sum(ledger["opening_balance_paise"] for ledger in ledgers)
        return {"date_from": date_from, "date_to": date_to, "rows": rows, "totals": totals,
                "balanced": totals["debit_paise"] == totals["credit_paise"] and totals["closing_paise"] == opening_difference,
                "opening_difference_paise": opening_difference}

    async def statement(self, ledger_id: uuid.UUID, date_from: date, date_to: date) -> Dict[str, Any]:
        ledger = await self.session.get(Ledger, ledger_id)
        if ledger is None:
            raise AccountsError("Ledger not found.", status_code=404)
        before = (await self._movements(date_to=date_from - timedelta(days=1))).get(ledger.id, (0, 0))
        opening = ledger.opening_balance_paise + before[0] - before[1]
        balance = opening
        rows = []
        for line, voucher in (await self.session.execute(
            select(VoucherLine, Voucher).join(Voucher, Voucher.id == VoucherLine.voucher_id)
            .where(VoucherLine.ledger_id == ledger.id, Voucher.voucher_date >= date_from,
                   Voucher.voucher_date <= date_to)
            .order_by(Voucher.voucher_date, Voucher.created_at, VoucherLine.position)
        )).all():
            balance += line.debit_paise - line.credit_paise
            rows.append({"voucher_id": voucher.id, "voucher_number": voucher.voucher_number,
                         "voucher_type": voucher.voucher_type, "voucher_date": voucher.voucher_date,
                         "narration": line.narration or voucher.narration, "status": voucher.status,
                         "debit_paise": line.debit_paise, "credit_paise": line.credit_paise,
                         "balance_paise": balance})
        row = next(item for item in await self.ledgers() if item["id"] == ledger.id)
        return {"ledger": row, "date_from": date_from, "date_to": date_to, "opening_paise": opening,
                "rows": rows, "closing_paise": balance,
                "total_debit_paise": sum(r["debit_paise"] for r in rows),
                "total_credit_paise": sum(r["credit_paise"] for r in rows)}

    async def vouchers(self, *, date_from: date, date_to: date, voucher_type: Optional[str] = None,
                       q: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        totals = (select(VoucherLine.voucher_id, func.sum(VoucherLine.debit_paise).label("amount"))
                  .group_by(VoucherLine.voucher_id).subquery())
        statement = (select(Voucher, totals.c.amount).join(totals, totals.c.voucher_id == Voucher.id)
                     .where(Voucher.voucher_date >= date_from, Voucher.voucher_date <= date_to))
        if voucher_type:
            statement = statement.where(Voucher.voucher_type == voucher_type)
        if q:
            like = f"%{q.strip()}%"
            statement = statement.where(Voucher.voucher_number.ilike(like) | Voucher.narration.ilike(like))
        found = (await self.session.execute(
            statement.order_by(Voucher.voucher_date.desc(), Voucher.created_at.desc()).limit(limit))).all()
        return [self._voucher_row(voucher, int(amount or 0)) for voucher, amount in found]

    @staticmethod
    def _voucher_row(voucher: Voucher, amount: int) -> Dict[str, Any]:
        return {
            "id": voucher.id, "voucher_number": voucher.voucher_number, "voucher_type": voucher.voucher_type,
            "financial_year": voucher.financial_year, "voucher_date": voucher.voucher_date,
            "narration": voucher.narration, "source_type": voucher.source_type, "source_id": voucher.source_id,
            "status": voucher.status, "reversal_of_id": voucher.reversal_of_id, "is_manual": voucher.is_manual,
            "created_by_name": voucher.created_by_name, "reversed_at": voucher.reversed_at,
            "reversed_by_name": voucher.reversed_by_name, "reversal_reason": voucher.reversal_reason,
            "total_paise": amount, "created_at": voucher.created_at,
        }

    async def voucher(self, voucher_id: uuid.UUID) -> Dict[str, Any]:
        voucher = await self.session.get(Voucher, voucher_id)
        if voucher is None:
            raise AccountsError("Voucher not found.", status_code=404)
        found = (await self.session.execute(
            select(VoucherLine, Ledger).join(Ledger, Ledger.id == VoucherLine.ledger_id)
            .where(VoucherLine.voucher_id == voucher.id).order_by(VoucherLine.position))).all()
        row = self._voucher_row(voucher, sum(line.debit_paise for line, _ in found))
        row["lines"] = [{"ledger_id": ledger.id, "ledger_name": ledger.name, "ledger_code": ledger.code,
                         "debit_paise": line.debit_paise, "credit_paise": line.credit_paise,
                         "narration": line.narration} for line, ledger in found]
        return row

    # ============================================================ writing
    async def create_manual(self, *, voucher_type: str, on: date, narration: str,
                            lines: List[Dict[str, Any]], created_by_name: str) -> Voucher:
        if voucher_type not in MANUAL_TYPES:
            raise AccountsError("A manual voucher is a journal, payment, receipt or contra.")
        if on > local_today():
            raise AccountsError("A voucher cannot be dated in the future.")
        if len((narration or "").strip()) < 3:
            raise AccountsError("Say what the voucher is for.")
        await self.ensure_chart()
        drafted = []
        for entry in lines:
            ledger = await self.session.get(Ledger, uuid.UUID(str(entry["ledger_id"])))
            if ledger is None:
                raise AccountsError("One of the ledgers no longer exists.")
            drafted.append(posting.Line(f"ledger:{ledger.id}", debit=int(entry.get("debit_paise") or 0),
                                        credit=int(entry.get("credit_paise") or 0),
                                        narration=(entry.get("narration") or None)))
        draft = posting.Draft(voucher_type, on, narration.strip(), drafted)
        voucher = await self.post(draft, source_type="manual", created_by_name=created_by_name, is_manual=True)
        return voucher

    async def reverse_manual(self, voucher_id: uuid.UUID, *, reason: str, by: str) -> Voucher:
        voucher = (await self.session.execute(
            select(Voucher).where(Voucher.id == voucher_id).with_for_update())).scalar_one_or_none()
        if voucher is None:
            raise AccountsError("Voucher not found.", status_code=404)
        if not voucher.is_manual:
            raise AccountsError("This voucher was posted from a bill, receipt or payout. Correct it there: "
                                "amend, cancel or refund, and the books follow.")
        if len((reason or "").strip()) < 3:
            raise AccountsError("Give a reason for the reversal.")
        return await self.reverse(voucher, on=local_today(), reason=reason.strip(), by=by)

    async def save_ledger(self, ledger_id: Optional[uuid.UUID], data: Dict[str, Any]) -> Ledger:
        await self.ensure_chart()
        name = (data.get("name") or "").strip()
        code = (data.get("code") or "").strip().upper()
        if len(name) < 2 or not code:
            raise AccountsError("A ledger needs a name and a code.")
        ledger = None
        if ledger_id is not None:
            ledger = await self.session.get(Ledger, ledger_id)
            if ledger is None:
                raise AccountsError("Ledger not found.", status_code=404)
        group = await self.session.get(AccountGroup, uuid.UUID(str(data["group_id"])))
        if group is None:
            raise AccountsError("Choose a group.")
        clash = (await self.session.execute(select(Ledger).where(
            (func.lower(Ledger.name) == name.lower()) | (func.upper(Ledger.code) == code)))).scalars()
        if any(other.id != ledger_id for other in clash):
            raise AccountsError("Another ledger already has that name or code.", status_code=409)
        if ledger is None:
            ledger = Ledger(group_id=group.id, is_system=False)
            self.session.add(ledger)
        elif ledger.is_system:
            if group.id != ledger.group_id or not data.get("is_active", True):
                raise AccountsError("A ledger the posting engine writes to cannot be moved or closed. "
                                    "It can be renamed and given an opening balance.")
        ledger.name = name
        ledger.code = code
        ledger.group_id = group.id
        ledger.opening_balance_paise = int(data.get("opening_balance_paise") or 0)
        ledger.is_active = bool(data.get("is_active", True))
        ledger.notes = (data.get("notes") or "").strip() or None
        await self.session.flush()
        return ledger
