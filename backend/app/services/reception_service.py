"""Reception: registration, visits, billing and collection.

The counter workflow this supports, in order:

    find or register the patient  ->  UHID
    open a visit for today        ->  visit number + token
    raise the invoice             ->  invoice number
    take payment                  ->  receipt number
    hand over the token slip      ->  patient goes to the voice intake

Numbering is the part that needs care. Invoice and receipt numbers must be
sequential and gapless within a financial year, so they come from a counter row
locked FOR UPDATE. `max(number) + 1` would look equivalent and would produce
duplicates the first time two cashiers billed at the same moment.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, delete, func, or_, select, true as sa_true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.billing.engine import (
    BillingError,
    LineInput,
    compute_invoice,
    validate_payment,
)
from app.billing.pricing import (
    PriceDecision,
    PricingContext,
    build_context as build_pricing_context,
    decide as price_decide,
    explain as price_explain,
)
from app.billing.payment_modes import (
    PaymentModeError,
    summarise as summarise_mode,
    validate_mode_details,
)
from app.billing.identifiers import (
    build_invoice_number,
    build_receipt_number,
    build_uhid,
    financial_year,
    normalise_uhid,
)
from app.core.clock import day_bounds, local_today
from app.core.logging import get_logger
from app.models.emr import (
    CashSession,
    PatientWallet,
    WalletEntry,
    DocumentCounter,
    Invoice,
    InvoiceLine,
    Payment,
    ServiceItem,
    Visit,
)
from app.models.enums import (
    CashSessionStatus,
    Department,
    Gender,
    InvoiceStatus,
    PayerType,
    PaymentMode,
    VisitStatus,
    VisitType,
    WalletEntryKind,
)
from app.models.patient import Patient

logger = get_logger(__name__)


# Optional demographics a patient record may carry. Named explicitly so that a
# field added to the API schema but not to the model fails loudly at
# registration instead of being dropped on the floor.
OPTIONAL_PATIENT_FIELDS = frozenset({
    "date_of_birth", "address", "city", "blood_group",
    "emergency_contact_name", "emergency_contact_phone",
    "title", "guardian_relation", "guardian_name", "email",
    "govt_id_type", "govt_id_number",
    "state", "country", "pincode",
    "religion", "marital_status", "nationality", "occupation",
    "category", "group_one", "group_two",
})


class ReceptionError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReceptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------------------------------------------------- numbering
    async def _next_sequence(self, scope: str, period: str) -> int:
        """Allocate the next number in a sequence, safely under concurrency.

        The row is locked FOR UPDATE for the remainder of the transaction, so
        a second cashier billing at the same instant waits rather than reading
        the same value. This is the difference between a gapless sequence and
        two invoices sharing a number.
        """
        result = await self.session.execute(
            select(DocumentCounter)
            .where(DocumentCounter.scope == scope, DocumentCounter.period == period)
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            # The insert goes inside a SAVEPOINT. If another cashier created
            # the same counter a moment earlier, only this insert is undone —
            # a full session rollback would expire every object the caller is
            # holding, including the authenticated user, and the next
            # attribute access would fail with MissingGreenlet.
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope=scope, period=period, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = None

            if counter is None:
                result = await self.session.execute(
                    select(DocumentCounter)
                    .where(
                        DocumentCounter.scope == scope,
                        DocumentCounter.period == period,
                    )
                    .with_for_update()
                )
                counter = result.scalar_one()

        counter.last_value += 1
        await self.session.flush()
        return counter.last_value

    # ---------------------------------------------------------- patients
    async def find_patients(
        self, query: str, *, limit: int = 20
    ) -> Sequence[Patient]:
        """Look a patient up by UHID, phone or name — whatever staff have.

        UHID is tried first and exactly: at a busy counter the patient usually
        hands over a card or an old prescription, and an exact hit should not
        be buried among name matches.
        """
        term = (query or "").strip()
        if not term:
            return []

        candidate = normalise_uhid(term)
        if candidate.startswith("SAT"):
            result = await self.session.execute(
                select(Patient).where(Patient.uhid == candidate)
            )
            exact = result.scalar_one_or_none()
            if exact is not None:
                return [exact]

        digits = "".join(character for character in term if character.isdigit())
        clauses = [Patient.name.ilike(f"%{term}%")]
        if len(digits) >= 4:
            clauses.append(Patient.phone_number.ilike(f"%{digits}%"))

        result = await self.session.execute(
            select(Patient)
            .where(func.coalesce(Patient.uhid, "") != "")
            .where(clauses[0] if len(clauses) == 1 else (clauses[0] | clauses[1]))
            .order_by(Patient.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def register_patient(
        self,
        *,
        name: str,
        age: int,
        gender: Gender,
        phone_number: str,
        **demographics: Any,
    ) -> Patient:
        """Create a patient and issue their permanent UHID.

        Everything beyond name, age, sex and mobile is optional here. Which of
        those the counter must actually fill in is configured per hospital and
        enforced by the registration form, not hardcoded into this signature.
        """
        if not (name or "").strip():
            raise ReceptionError("The patient's name is required.")
        if age < 0 or age > 120:
            raise ReceptionError("Please check the age entered.")

        unknown = set(demographics) - OPTIONAL_PATIENT_FIELDS
        if unknown:
            # Caught here rather than swallowed: a field added to the schema
            # but not to the model would otherwise be silently discarded, and
            # the counter would have no idea the data never landed.
            raise ReceptionError(
                "Unknown patient fields: " + ", ".join(sorted(unknown))
            )

        sequence = await self._next_sequence("uhid", "all")
        patient = Patient(
            uhid=build_uhid(sequence),
            name=name.strip(),
            age=age,
            gender=gender,
            phone_number=(phone_number or "").strip(),
            **demographics,
        )
        self.session.add(patient)
        await self.session.flush()
        logger.info("patient_registered", extra={"uhid": patient.uhid})
        return patient

    # ------------------------------------------------------------ visits
    async def _next_token(self, on: date, department: Department) -> int:
        """The next queue position for a department today."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Visit)
            .where(Visit.visit_date == on, Visit.department == department)
        )
        return int(result.scalar_one()) + 1

    async def open_visit(
        self,
        *,
        patient_id: uuid.UUID,
        department: Department,
        doctor_id: Optional[uuid.UUID],
        doctor_name: str,
        visit_type: VisitType = VisitType.NEW,
        payer_type: PayerType = PayerType.SELF_PAY,
        referred_by: Optional[str] = None,
        registered_by_name: str = "",
        notes: Optional[str] = None,
    ) -> Visit:
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise ReceptionError("Patient not found.")

        today = local_today()
        sequence = await self._next_sequence("visit", today.isoformat())
        visit = Visit(
            visit_number=f"V{today:%y%m%d}-{sequence:04d}",
            patient_id=patient_id,
            department=department,
            doctor_id=doctor_id,
            doctor_name=doctor_name,
            visit_type=visit_type,
            payer_type=payer_type,
            status=VisitStatus.REGISTERED,
            visit_date=today,
            token_number=await self._next_token(today, department),
            referred_by=referred_by,
            registered_by_name=registered_by_name,
            notes=notes,
        )
        self.session.add(visit)
        await self.session.flush()
        logger.info(
            "visit_opened",
            extra={"visit": visit.visit_number, "uhid": patient.uhid,
                   "department": department.value, "token": visit.token_number},
        )
        return visit

    async def _price_items(
        self,
        items: List[Dict[str, Any]],
        *,
        context: Optional[PricingContext] = None,
    ) -> Tuple[List[LineInput], List[str]]:
        """Resolve each requested item against the tariff and the rules.

        Shared by raising a bill and amending one, so a correction is priced
        by exactly the rules that priced the original. The resolved values
        are copied onto the invoice line afterwards: a tariff revision next
        month must not change what a patient was charged today.

        Returns the priced lines and the reasons worth showing — a line that
        came out free has to be able to say why.
        """
        context = context or PricingContext()
        decisions: List[PriceDecision] = []
        lines: List[LineInput] = []
        for entry in items:
            service: Optional[ServiceItem] = None
            if entry.get("service_item_id"):
                service = await self.session.get(
                    ServiceItem, uuid.UUID(str(entry["service_item_id"]))
                )
            # A screen opened before the price list was rebuilt holds ids that
            # no longer exist. The code still identifies the same charge, so
            # the live service is found that way and the tariff and the
            # pricing rules apply exactly as they would have.
            if service is None and entry.get("code"):
                result = await self.session.execute(
                    select(ServiceItem).where(ServiceItem.code == entry["code"])
                )
                service = result.scalar_one_or_none()

            description = entry.get("description") or (service.name if service else "")
            if not description:
                # Almost always a screen opened before the price list changed,
                # holding an id that no longer exists. Saying so is the
                # difference between a clerk reloading and a clerk stuck.
                if entry.get("service_item_id") and service is None:
                    raise ReceptionError(
                        "That charge is no longer in the price list. Reload the "
                        "counter and add it again."
                    )
                raise ReceptionError("Every billed item needs a description.")

            if entry.get("unit_rate_paise") is None and service is None:
                raise ReceptionError(f"No rate available for {description}.")

            # The rules live in app/billing/pricing.py, not here: the counter,
            # the quote endpoint and an amendment must all reach the same
            # figure, and three copies of "is this a free follow-up" would
            # not stay in agreement.
            decision = price_decide(
                service=service,
                context=context,
                explicit_rate_paise=entry.get("unit_rate_paise"),
            )
            decisions.append(decision)
            rate = decision.rate_paise

            lines.append(
                LineInput(
                    description=description,
                    unit_rate_paise=int(rate),
                    quantity=int(entry.get("quantity") or 1),
                    tax_percent=int(
                        entry.get("tax_percent")
                        if entry.get("tax_percent") is not None
                        else (service.tax_percent if service else 0)
                    ),
                    discount_paise=int(entry.get("discount_paise") or 0),
                    code=entry.get("code") or (service.code if service else None),
                    hsn_sac_code=service.hsn_sac_code if service else None,
                    service_item_id=str(service.id) if service else None,
                    remark=(entry.get("remark") or None),
                )
            )
        return lines, price_explain(decisions)

    def _apply_totals(self, invoice: Invoice, computed: Any) -> None:
        """Copy computed totals onto the invoice, in one place.

        Every field, every time. Setting a subset is how an amended bill ends
        up carrying a new total beside the previous tax figures.
        """
        invoice.gross_paise = computed.gross_paise
        invoice.discount_paise = computed.discount_paise
        invoice.taxable_paise = computed.taxable_paise
        invoice.cgst_paise = computed.cgst_paise
        invoice.sgst_paise = computed.sgst_paise
        invoice.igst_paise = computed.igst_paise
        invoice.total_paise = computed.total_paise

    def _write_lines(self, invoice: Invoice, computed: Any) -> None:
        for position, line in enumerate(computed.lines):
            self.session.add(
                InvoiceLine(
                    invoice_id=invoice.id,
                    position=position,
                    service_item_id=(
                        uuid.UUID(line.service_item_id) if line.service_item_id else None
                    ),
                    code=line.code,
                    description=line.description,
                    remark=line.remark,
                    hsn_sac_code=line.hsn_sac_code,
                    quantity=line.quantity,
                    unit_rate_paise=line.unit_rate_paise,
                    discount_paise=line.discount_paise,
                    tax_percent=line.tax_percent,
                    taxable_paise=line.taxable_paise,
                    tax_paise=line.tax_paise,
                    total_paise=line.total_paise,
                )
            )

    # ----------------------------------------------------------- billing
    async def create_invoice(
        self,
        *,
        visit_id: Optional[uuid.UUID],
        patient_id: uuid.UUID,
        items: List[Dict[str, Any]],
        invoice_discount_paise: int = 0,
        discount_reason: Optional[str] = None,
        discount_approved_by: Optional[str] = None,
        payer_type: PayerType = PayerType.SELF_PAY,
        payer_covered_paise: int = 0,
        # Who the patient is being seen by and under whose agreement, so the
        # consultant's free-follow-up window and the organisation's rate card
        # can be applied without the counter having to know them.
        consultant_id: Optional[uuid.UUID] = None,
        doctor_name: Optional[str] = None,
        organisation_id: Optional[uuid.UUID] = None,
        created_by_name: str = "",
        issue: bool = True,
    ) -> Invoice:
        """Price the visit and raise the bill.

        Rates come from the tariff when a service is chosen by code, but the
        resolved values are written onto the invoice lines — the bill must not
        change if the tariff is revised next month.
        """
        context = await build_pricing_context(
            self.session,
            patient_id=patient_id,
            consultant_id=consultant_id,
            doctor_name=doctor_name,
            organisation_id=organisation_id,
        )
        lines, pricing_notes = await self._price_items(items, context=context)

        try:
            computed = compute_invoice(
                lines, invoice_discount_paise=invoice_discount_paise
            )
        except BillingError as exc:
            raise ReceptionError(str(exc)) from exc

        today = local_today()
        sequence = await self._next_sequence("invoice", financial_year(today))
        invoice = Invoice(
            invoice_number=build_invoice_number(sequence, today),
            visit_id=visit_id,
            patient_id=patient_id,
            status=InvoiceStatus.ISSUED if issue else InvoiceStatus.DRAFT,
            payer_type=payer_type,
            gross_paise=computed.gross_paise,
            discount_paise=computed.discount_paise,
            taxable_paise=computed.taxable_paise,
            cgst_paise=computed.cgst_paise,
            sgst_paise=computed.sgst_paise,
            igst_paise=computed.igst_paise,
            total_paise=computed.total_paise,
            payer_covered_paise=payer_covered_paise,
            discount_reason=discount_reason,
            discount_approved_by=discount_approved_by,
            organisation_id=organisation_id,
            consultant_id=(context.consultant.id if context.consultant else None),
            doctor_name=doctor_name or (
                context.consultant.full_name if context.consultant else ""
            ),
            # Why anything on this bill was priced the way it was. Stored
            # rather than recomputed, because the rules change and the bill
            # must still explain itself next year.
            pricing_notes=pricing_notes or None,
            issued_at=_now() if issue else None,
            created_by_name=created_by_name,
        )
        self.session.add(invoice)
        await self.session.flush()

        self._write_lines(invoice, computed)
        await self.session.flush()
        logger.info(
            "invoice_created",
            extra={"invoice": invoice.invoice_number, "total_paise": invoice.total_paise},
        )
        return invoice

    async def record_payment(
        self,
        *,
        invoice_id: uuid.UUID,
        amount_paise: int,
        mode: PaymentMode,
        reference: Optional[str] = None,
        mode_details: Optional[Dict[str, Any]] = None,
        received_by_id: Optional[uuid.UUID] = None,
        received_by_name: str = "",
        cash_session_id: Optional[uuid.UUID] = None,
    ) -> Payment:
        if mode is PaymentMode.WALLET:
            # Spending a wallet has to go through pay_from_wallet, which
            # locks the balance and writes the ledger entry. Allowed here it
            # would credit the invoice without ever debiting the patient.
            raise ReceptionError(
                "Use the wallet to pay this bill, so the balance is debited too."
            )
        try:
            details = validate_mode_details(mode, mode_details)
        except PaymentModeError as exc:
            raise ReceptionError(str(exc)) from exc

        invoice = await self._lock_invoice(invoice_id)
        if invoice is None:
            raise ReceptionError("Invoice not found.")
        if invoice.status is InvoiceStatus.CANCELLED:
            raise ReceptionError("This invoice has been cancelled.")

        try:
            validate_payment(
                amount_paise=amount_paise, balance_paise=invoice.balance_paise
            )
        except BillingError as exc:
            raise ReceptionError(str(exc)) from exc

        today = local_today()
        sequence = await self._next_sequence("receipt", financial_year(today))
        payment = Payment(
            receipt_number=build_receipt_number(sequence, today),
            invoice_id=invoice_id,
            cash_session_id=cash_session_id,
            amount_paise=amount_paise,
            mode=mode,
            reference=reference,
            mode_details=details or None,
            received_at=_now(),
            received_by_id=received_by_id,
            received_by_name=received_by_name,
        )
        self.session.add(payment)

        invoice.paid_paise += amount_paise
        invoice.status = (
            InvoiceStatus.PAID
            if invoice.paid_paise >= invoice.total_paise
            else InvoiceStatus.PARTIALLY_PAID
        )
        await self.session.flush()
        logger.info(
            "payment_recorded",
            extra={"receipt": payment.receipt_number, "invoice": invoice.invoice_number,
                   "amount_paise": amount_paise, "mode": mode.value},
        )
        return payment

    # ------------------------------------------------------------- wallet
    async def _wallet(self, patient_id: uuid.UUID, *, lock: bool = True) -> PatientWallet:
        """The patient's balance row, created on first use and locked.

        Locking is the whole point. Reading a balance, deciding it is
        sufficient, and then debiting it is three steps; without the lock a
        second counter can slip between them and both spend the same money,
        which is exactly how a wallet goes negative.
        """
        stmt = select(PatientWallet).where(PatientWallet.patient_id == patient_id)
        if lock:
            stmt = stmt.with_for_update()
        wallet = await self.session.scalar(stmt)
        if wallet is not None:
            return wallet

        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise ReceptionError("Patient not found.")
        wallet = PatientWallet(patient_id=patient_id, balance_paise=0)
        self.session.add(wallet)
        await self.session.flush()
        return wallet

    async def _wallet_move(
        self,
        *,
        wallet: PatientWallet,
        kind: WalletEntryKind,
        amount_paise: int,
        reason: Optional[str] = None,
        invoice_id: Optional[uuid.UUID] = None,
        payment_id: Optional[uuid.UUID] = None,
        receipt_number: Optional[str] = None,
        created_by_name: str = "",
        mode: Optional[PaymentMode] = None,
        admission_id: Optional[uuid.UUID] = None,
    ) -> WalletEntry:
        """Apply a signed movement and append the ledger line for it."""
        new_balance = wallet.balance_paise + amount_paise
        if new_balance < 0:
            raise ReceptionError(
                "That is more than the wallet holds "
                f"({wallet.balance_paise / 100:.2f} available)."
            )
        wallet.balance_paise = new_balance
        entry = WalletEntry(
            wallet_id=wallet.id,
            patient_id=wallet.patient_id,
            kind=kind,
            amount_paise=amount_paise,
            balance_after_paise=new_balance,
            invoice_id=invoice_id,
            payment_id=payment_id,
            receipt_number=receipt_number,
            reason=reason,
            created_by_name=created_by_name,
            mode=mode,
            admission_id=admission_id,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def wallet_balance(self, patient_id: uuid.UUID) -> int:
        wallet = await self.session.scalar(
            select(PatientWallet).where(PatientWallet.patient_id == patient_id)
        )
        return wallet.balance_paise if wallet else 0

    async def wallet_statement(
        self, patient_id: uuid.UUID, *, limit: int = 100
    ) -> Tuple[int, Sequence[WalletEntry]]:
        wallet = await self.session.scalar(
            select(PatientWallet).where(PatientWallet.patient_id == patient_id)
        )
        if wallet is None:
            return 0, []
        result = await self.session.execute(
            select(WalletEntry)
            .where(WalletEntry.patient_id == patient_id)
            .order_by(WalletEntry.created_at.desc())
            .limit(limit)
        )
        return wallet.balance_paise, list(result.scalars())

    async def wallet_deposit(
        self,
        *,
        patient_id: uuid.UUID,
        amount_paise: int,
        mode: PaymentMode = PaymentMode.CASH,
        mode_details: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        received_by_name: str = "",
        admission_id: Optional[uuid.UUID] = None,
    ) -> WalletEntry:
        """Take an advance and put it on the patient's account.

        This is real money arriving, so it gets a receipt number from the
        same gapless series as any other collection - the patient walks away
        holding proof, and the day's cash counts it once, here.
        """
        if amount_paise <= 0:
            raise ReceptionError("A deposit must be for more than zero.")
        if mode is PaymentMode.WALLET:
            raise ReceptionError("A wallet cannot be topped up from itself.")
        if mode is PaymentMode.WAIVER:
            raise ReceptionError(
                "A waiver is money never collected; it cannot be deposited."
            )
        try:
            details = validate_mode_details(mode, mode_details)
        except PaymentModeError as exc:
            raise ReceptionError(str(exc)) from exc

        wallet = await self._wallet(patient_id)
        today = local_today()
        sequence = await self._next_sequence("receipt", financial_year(today))
        receipt_number = build_receipt_number(sequence, today)

        entry = await self._wallet_move(
            wallet=wallet,
            kind=WalletEntryKind.DEPOSIT,
            amount_paise=amount_paise,
            reason=reason or summarise_mode(mode, details),
            receipt_number=receipt_number,
            created_by_name=received_by_name,
            mode=mode,
            admission_id=admission_id,
        )
        logger.info(
            "wallet_deposit",
            extra={"receipt": receipt_number, "amount_paise": amount_paise,
                   "balance_paise": wallet.balance_paise},
        )
        return entry

    async def wallet_withdraw(
        self,
        *,
        patient_id: uuid.UUID,
        amount_paise: int,
        reason: str,
        received_by_name: str = "",
    ) -> WalletEntry:
        """Hand the balance back. Money leaving the till, so it is a refund."""
        if amount_paise <= 0:
            raise ReceptionError("A withdrawal must be for more than zero.")
        if not (reason or "").strip():
            raise ReceptionError("A withdrawal needs a reason.")

        wallet = await self._wallet(patient_id)
        today = local_today()
        sequence = await self._next_sequence("receipt", financial_year(today))
        receipt_number = build_receipt_number(sequence, today)

        entry = await self._wallet_move(
            wallet=wallet,
            kind=WalletEntryKind.WITHDRAWAL,
            amount_paise=-amount_paise,
            reason=reason.strip(),
            receipt_number=receipt_number,
            created_by_name=received_by_name,
            mode=PaymentMode.CASH,
        )
        logger.info(
            "wallet_withdrawal",
            extra={"receipt": receipt_number, "amount_paise": amount_paise,
                   "balance_paise": wallet.balance_paise},
        )
        return entry

    async def pay_from_wallet(
        self,
        *,
        invoice_id: uuid.UUID,
        amount_paise: int,
        received_by_id: Optional[uuid.UUID] = None,
        received_by_name: str = "",
    ) -> Payment:
        """Settle a bill from credit the patient already left.

        Written as both a payment and a wallet debit in one transaction. If
        only one of the two landed, the hospital would either be paid twice
        or not at all - and nobody would notice until the balance was queried
        at the counter weeks later.
        """
        invoice = await self._lock_invoice(invoice_id)
        if invoice is None:
            raise ReceptionError("Invoice not found.")
        if invoice.status is InvoiceStatus.CANCELLED:
            raise ReceptionError("This invoice has been cancelled.")
        try:
            validate_payment(
                amount_paise=amount_paise, balance_paise=invoice.balance_paise
            )
        except BillingError as exc:
            raise ReceptionError(str(exc)) from exc

        # Locked after the invoice, and every wallet path takes them in this
        # order - invoice then wallet - so two counters cannot deadlock by
        # each holding one and waiting for the other.
        wallet = await self._wallet(invoice.patient_id)

        today = local_today()
        sequence = await self._next_sequence("receipt", financial_year(today))
        payment = Payment(
            receipt_number=build_receipt_number(sequence, today),
            invoice_id=invoice_id,
            amount_paise=amount_paise,
            mode=PaymentMode.WALLET,
            received_at=_now(),
            received_by_id=received_by_id,
            received_by_name=received_by_name,
        )
        self.session.add(payment)
        await self.session.flush()

        await self._wallet_move(
            wallet=wallet,
            kind=WalletEntryKind.APPLIED,
            amount_paise=-amount_paise,
            reason=f"Applied to {invoice.invoice_number}",
            invoice_id=invoice_id,
            payment_id=payment.id,
            receipt_number=payment.receipt_number,
            created_by_name=received_by_name,
        )

        invoice.paid_paise += amount_paise
        invoice.status = (
            InvoiceStatus.PAID
            if invoice.paid_paise >= invoice.total_paise
            else InvoiceStatus.PARTIALLY_PAID
        )
        await self.session.flush()
        return payment

    async def refund(
        self,
        *,
        invoice_id: uuid.UUID,
        amount_paise: int,
        reason: str,
        mode: PaymentMode = PaymentMode.CASH,
        to_wallet: bool = False,
        received_by_name: str = "",
    ) -> Payment:
        """Return money as a negative payment rather than by deleting one.

        The original receipt stays in the record, so what was taken and what
        was given back are both auditable.

        `to_wallet` credits the patient instead of opening the drawer. It is
        the honest answer to the commonest refund at an OPD counter — a test
        that was billed and then not done, for a patient who is coming back
        on Thursday anyway — and it keeps the cash where it already is
        instead of paying it out and taking it in again.
        """
        invoice = await self._lock_invoice(invoice_id)
        if invoice is None:
            raise ReceptionError("Invoice not found.")
        if amount_paise <= 0:
            raise ReceptionError("A refund must be for more than zero.")
        if amount_paise > invoice.paid_paise:
            raise ReceptionError("That is more than was collected on this invoice.")
        if not (reason or "").strip():
            raise ReceptionError("A refund needs a reason.")

        if to_wallet:
            # Recorded as a wallet-mode refund so the day's cash figure does
            # not show money going out of a drawer that never opened.
            mode = PaymentMode.WALLET

        today = local_today()
        sequence = await self._next_sequence("receipt", financial_year(today))
        refund = Payment(
            receipt_number=build_receipt_number(sequence, today),
            invoice_id=invoice_id,
            amount_paise=-amount_paise,
            mode=mode,
            received_at=_now(),
            received_by_name=received_by_name,
            is_refund=True,
            refund_reason=reason.strip(),
        )
        self.session.add(refund)
        await self.session.flush()

        if to_wallet:
            wallet = await self._wallet(invoice.patient_id)
            await self._wallet_move(
                wallet=wallet,
                kind=WalletEntryKind.REFUND_CREDIT,
                amount_paise=amount_paise,
                reason=f"Refund on {invoice.invoice_number}: {reason.strip()}",
                invoice_id=invoice_id,
                payment_id=refund.id,
                receipt_number=refund.receipt_number,
                created_by_name=received_by_name,
            )

        invoice.paid_paise -= amount_paise
        if invoice.paid_paise <= 0:
            invoice.status = InvoiceStatus.REFUNDED
        elif invoice.paid_paise < invoice.total_paise:
            invoice.status = InvoiceStatus.PARTIALLY_PAID
        await self.session.flush()
        return refund

    async def cancel_invoice(
        self, invoice_id: uuid.UUID, *, reason: str
    ) -> Invoice:
        """Cancel a bill. The number is retained, never reused.

        Reusing a cancelled number would break the sequence an auditor checks;
        a cancelled invoice must remain visible as cancelled.
        """
        invoice = await self._lock_invoice(invoice_id)
        if invoice is None:
            raise ReceptionError("Invoice not found.")
        if invoice.status is InvoiceStatus.CANCELLED:
            raise ReceptionError("This bill is already cancelled.")
        await self._refuse_if_payout_locked(invoice)
        if invoice.paid_paise != 0:
            raise ReceptionError(
                "Refund the collected amount before cancelling this invoice."
            )
        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancelled_at = _now()
        invoice.cancellation_reason = reason
        await self.session.flush()
        return invoice

    async def _lock_invoice(self, invoice_id: uuid.UUID) -> Optional[Invoice]:
        """Take the invoice row for update before touching its balance.

        Without this, two cashiers collecting the same bill at the same moment
        both read paid=0 and both write paid=total: two receipts are printed,
        the patient is charged twice, and the ledger records one payment. The
        drawer is then over at closing time with nothing to explain it.

        Holding the row lock makes the read-modify-write sequence atomic, so
        the second attempt sees the first one's result and is correctly
        rejected as an overpayment.
        """
        result = await self.session.execute(
            select(Invoice).where(Invoice.id == invoice_id).with_for_update()
        )
        return result.scalar_one_or_none()

    # --------------------------------------------------------- retrieval
    async def find_invoices(
        self,
        *,
        q: Optional[str] = None,
        patient_id: Optional[uuid.UUID] = None,
        status: Optional[InvoiceStatus] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Find past bills, the way somebody at the counter would ask for one.

        The patient is joined in rather than fetched per row. A bill list
        that shows only invoice numbers is unusable — staff look up "the bill
        for Mrs Sharma yesterday", not SAT/26-27/000214 — and issuing one
        query per line to get the name would make a fifty-row page fifty-one
        round trips.
        """
        conditions = []
        if patient_id is not None:
            conditions.append(Invoice.patient_id == patient_id)
        if status is not None:
            conditions.append(Invoice.status == status)
        if date_from is not None:
            conditions.append(Invoice.created_at >= day_bounds(date_from)[0])
        if date_to is not None:
            conditions.append(Invoice.created_at < day_bounds(date_to)[1])
        if q:
            term = q.strip()
            # An invoice number is exact; a name or a UHID is a prefix search
            # the clerk is halfway through typing.
            conditions.append(
                or_(
                    Invoice.invoice_number.ilike(f"%{term}%"),
                    Patient.uhid.ilike(f"{term}%"),
                    Patient.name.ilike(f"%{term}%"),
                    Patient.phone_number.ilike(f"{term}%"),
                )
            )

        where = and_(*conditions) if conditions else sa_true()

        total = await self.session.scalar(
            select(func.count())
            .select_from(Invoice)
            .join(Patient, Patient.id == Invoice.patient_id)
            .where(where)
        )

        result = await self.session.execute(
            select(Invoice, Patient, Visit)
            .join(Patient, Patient.id == Invoice.patient_id)
            .outerjoin(Visit, Visit.id == Invoice.visit_id)
            .where(where)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        rows: List[Dict[str, Any]] = []
        for invoice, patient, visit in result.all():
            rows.append({
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "status": invoice.status,
                "patient_id": patient.id,
                "patient_name": patient.name,
                "uhid": patient.uhid,
                "visit_number": visit.visit_number if visit else None,
                "visit_id": invoice.visit_id,
                "total_paise": invoice.total_paise,
                "paid_paise": invoice.paid_paise,
                "balance_paise": invoice.total_paise - invoice.paid_paise,
                "amendment_count": invoice.amendment_count,
                "payout_locked": invoice.payout_locked_at is not None,
                "issued_at": invoice.issued_at,
                "created_at": invoice.created_at,
            })
        return int(total or 0), rows

    async def get_invoice(self, invoice_id: uuid.UUID) -> Optional[Invoice]:
        result = await self.session.execute(
            select(Invoice)
            .options(selectinload(Invoice.lines), selectinload(Invoice.payments))
            .where(Invoice.id == invoice_id)
        )
        return result.scalar_one_or_none()

    async def get_visit(self, visit_id: uuid.UUID) -> Optional[Visit]:
        result = await self.session.execute(
            select(Visit)
            .options(selectinload(Visit.invoices).selectinload(Invoice.payments))
            .where(Visit.id == visit_id)
        )
        return result.scalar_one_or_none()

    async def todays_visits(
        self, *, department: Optional[Department] = None, on: Optional[date] = None
    ) -> List[Visit]:
        statement = (
            select(Visit, Patient.name)
            .join(Patient, Patient.id == Visit.patient_id)
            .where(Visit.visit_date == (on or local_today()))
            .order_by(Visit.token_number)
        )
        if department is not None:
            statement = statement.where(Visit.department == department)
        result = await self.session.execute(statement)
        visits: List[Visit] = []
        for visit, patient_name in result.all():
            # Not a mapped column — attached so VisitOut can read it straight
            # off the instance instead of the queue needing a second lookup.
            visit.patient_name = patient_name
            visits.append(visit)
        return visits

    async def intake_queue(
        self, *, department: Optional[Department] = None, on: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """Patients registered at the counter and waiting for voice intake.

        This is the handover between the two screens: reception registers and
        bills, and the intake terminal picks the patient up from here rather
        than asking them for their details a second time.

        Visits already linked to a consultation are excluded, so a patient
        cannot be started twice by two terminals.
        """
        day = on or local_today()
        statement = (
            select(Visit, Patient)
            .join(Patient, Patient.id == Visit.patient_id)
            .where(
                Visit.visit_date == day,
                Visit.status == VisitStatus.REGISTERED,
                Visit.visit_type == VisitType.NEW,
                Visit.consultation_id.is_(None),
            )
            .order_by(Visit.token_number)
        )
        if department is not None:
            statement = statement.where(Visit.department == department)

        rows = (await self.session.execute(statement)).all()
        return [
            {
                "visit_id": str(visit.id),
                "visit_number": visit.visit_number,
                "token_number": visit.token_number,
                "department": visit.department.value,
                "doctor_name": visit.doctor_name,
                "visit_type": visit.visit_type.value,
                "registered_at": visit.created_at.isoformat(),
                "patient": {
                    "id": str(patient.id),
                    "uhid": patient.uhid,
                    "name": patient.name,
                    "age": patient.age,
                    "gender": patient.gender.value,
                    "phone_number": patient.phone_number,
                },
            }
            for visit, patient in rows
        ]

    async def attach_consultation(
        self, visit_id: uuid.UUID, consultation_id: uuid.UUID
    ) -> Optional[Visit]:
        visit = await self.session.get(Visit, visit_id)
        if visit is None:
            return None
        visit.consultation_id = consultation_id
        visit.status = VisitStatus.IN_CONSULTATION
        await self.session.flush()
        return visit

    # ------------------------------------------------------ cash session
    # -------------------------------------------------------- corrections
    #
    # Undoing counter work has an order, and it is the reverse of the order
    # in which the work was done: a receipt is undone before its bill, and a
    # bill before the registration it belongs to. Enforced rather than
    # documented, because the failure mode is silent — a cancelled visit
    # still carrying a live invoice looks fine on both screens and wrong in
    # every report.
    #
    # One rule overrides all of it: once a consultant payout has counted an
    # invoice, nothing about it moves. Reversing it afterwards would change a
    # payment already made to a doctor.

    async def _refuse_if_payout_locked(self, invoice: Invoice) -> None:
        if invoice.payout_locked_at is not None:
            raise ReceptionError(
                f"{invoice.invoice_number} has already been settled in a consultant "
                "payout and can no longer be changed. Raise a credit note instead."
            )

    async def cancel_receipt(
        self, payment_id: uuid.UUID, *, reason: str, cancelled_by_name: str = ""
    ) -> Payment:
        """Strike out a receipt that should never have been entered.

        Deliberately not a refund. A refund says money went back to the
        patient; this says the entry was a mistake and no money moved —
        the wrong amount typed, the wrong mode, the wrong bill. Recording a
        keying error as a refund would show the hospital paying out cash it
        never paid.

        The cash-session guard is what keeps that honest. Once a shift is
        closed the drawer has been counted and handed over, so the money is
        real whatever the receipt says; from that point the only correct
        remedy is a refund.
        """
        if not (reason or "").strip():
            raise ReceptionError("Cancelling a receipt needs a reason.")

        payment = await self.session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if payment is None:
            raise ReceptionError("Receipt not found.")
        if payment.cancelled_at is not None:
            raise ReceptionError("This receipt has already been cancelled.")

        invoice = await self._lock_invoice(payment.invoice_id)
        if invoice is None:
            raise ReceptionError("The bill for this receipt no longer exists.")
        await self._refuse_if_payout_locked(invoice)

        if payment.cash_session_id is not None:
            session_row = await self.session.get(CashSession, payment.cash_session_id)
            if session_row is not None and session_row.status is not CashSessionStatus.OPEN:
                raise ReceptionError(
                    "That shift has been closed and the cash counted. Issue a refund "
                    "rather than cancelling the receipt."
                )

        payment.cancelled_at = _now()
        payment.cancellation_reason = reason.strip()
        payment.cancelled_by_name = cancelled_by_name

        # A cancelled refund puts the money back on the bill; a cancelled
        # collection takes it off. The sign already says which, so one line
        # covers both.
        invoice.paid_paise -= payment.amount_paise

        if payment.mode is PaymentMode.WALLET:
            # The credit was debited when this was recorded, so it has to go
            # back. Without this the patient is quietly out of pocket by the
            # amount of a receipt that no longer exists.
            wallet = await self._wallet(invoice.patient_id)
            # The payment's own sign already says which way to go, so one
            # expression covers both cases and they cannot disagree:
            #   spending credit  -> payment +500, wallet was debited 500,
            #                       reversal credits +500
            #   refund to wallet -> payment -500, wallet was credited 500,
            #                       reversal debits -500
            # Negating this was the bug: it debited the wallet a second time
            # and quietly left the patient short by the amount of a receipt
            # that no longer existed.
            await self._wallet_move(
                wallet=wallet,
                kind=WalletEntryKind.ADJUSTMENT,
                amount_paise=payment.amount_paise,
                reason=f"Receipt {payment.receipt_number} cancelled: {reason.strip()}",
                invoice_id=invoice.id,
                payment_id=payment.id,
                created_by_name=cancelled_by_name,
            )

        invoice.status = self._status_for(invoice)
        await self.session.flush()
        logger.info(
            "receipt_cancelled",
            extra={"receipt": payment.receipt_number, "invoice": invoice.invoice_number,
                   "amount_paise": payment.amount_paise},
        )
        return payment

    def _status_for(self, invoice: Invoice) -> InvoiceStatus:
        """What an invoice's status should be, given what it has been paid.

        Derived in one place so that collecting, refunding, cancelling a
        receipt and amending a bill cannot each arrive at a different answer
        for the same numbers.
        """
        if invoice.status is InvoiceStatus.CANCELLED:
            return InvoiceStatus.CANCELLED
        if invoice.paid_paise <= 0:
            return InvoiceStatus.ISSUED if invoice.issued_at else InvoiceStatus.DRAFT
        if invoice.paid_paise >= invoice.total_paise:
            return InvoiceStatus.PAID
        return InvoiceStatus.PARTIALLY_PAID

    async def uncancel_invoice(
        self, invoice_id: uuid.UUID, *, reason: str
    ) -> Invoice:
        """Reinstate a bill cancelled by mistake.

        The registration has to be live first. A bill standing against a
        cancelled visit is the inconsistency the cascade exists to prevent,
        and it is the exact case the old system named: the refund is
        uncancelled before its registration, never the other way round.
        """
        invoice = await self._lock_invoice(invoice_id)
        if invoice is None:
            raise ReceptionError("Invoice not found.")
        if invoice.status is not InvoiceStatus.CANCELLED:
            raise ReceptionError("This bill is not cancelled.")
        await self._refuse_if_payout_locked(invoice)

        if invoice.visit_id is not None:
            visit = await self.session.get(Visit, invoice.visit_id)
            if visit is not None and visit.status is VisitStatus.CANCELLED:
                raise ReceptionError(
                    f"Registration {visit.visit_number} is cancelled. Reinstate the "
                    "registration before its bill."
                )

        invoice.cancelled_at = None
        invoice.cancellation_reason = None
        # Cleared before asking, because _status_for reports CANCELLED for a
        # cancelled invoice — correct for every other caller, and exactly
        # wrong here.
        invoice.status = InvoiceStatus.ISSUED
        invoice.status = self._status_for(invoice)
        # Kept on the amendment trail rather than erased: a bill that was
        # cancelled and brought back is a fact somebody may have to explain.
        invoice.amended_at = _now()
        invoice.amendment_reason = f"Cancellation reversed: {reason.strip()}"
        invoice.amendment_count += 1
        await self.session.flush()
        return invoice

    async def amend_invoice(
        self,
        *,
        invoice_id: uuid.UUID,
        items: List[Dict[str, Any]],
        invoice_discount_paise: int = 0,
        discount_reason: Optional[str] = None,
        reason: str,
        amended_by_name: str = "",
    ) -> Invoice:
        """Correct a bill before anybody has paid it.

        Only before. Once money has been taken against an invoice its total
        is part of the day's collection and of a receipt the patient is
        holding; changing it then would leave a receipt that does not match
        its bill. The remedy after payment is a refund, or cancel and
        re-raise — both of which leave a trail.
        """
        if not (reason or "").strip():
            raise ReceptionError("An amendment needs a reason.")
        if not items:
            raise ReceptionError("A bill needs at least one charge.")

        invoice = await self._lock_invoice(invoice_id)
        if invoice is None:
            raise ReceptionError("Invoice not found.")
        if invoice.status is InvoiceStatus.CANCELLED:
            raise ReceptionError("This bill is cancelled. Reinstate it before editing.")
        await self._refuse_if_payout_locked(invoice)
        if invoice.paid_paise != 0:
            raise ReceptionError(
                "Money has already been taken against this bill. Refund it, or cancel "
                "the bill and raise a new one."
            )

        # Repriced against the same rules as the original, using the visit's
        # own consultant: a correction that quietly loses a free follow-up
        # would charge a patient who was told they would not be.
        context = await build_pricing_context(
            self.session,
            patient_id=invoice.patient_id,
            consultant_id=invoice.consultant_id,
            doctor_name=invoice.doctor_name or None,
            organisation_id=invoice.organisation_id,
        )
        priced, pricing_notes = await self._price_items(items, context=context)
        try:
            computed = compute_invoice(
                lines=priced, invoice_discount_paise=invoice_discount_paise
            )
        except BillingError as exc:
            raise ReceptionError(str(exc)) from exc

        # Replaced wholesale rather than diffed: the lines are a snapshot of
        # what was charged, and a partial update risks leaving a line from
        # the previous version that nobody meant to keep.
        #
        # Deleted by statement rather than through `invoice.lines`. The
        # invoice was loaded for update without its lines, so touching the
        # relationship would lazy-load inside async code and fail.
        await self.session.execute(
            delete(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
        )
        await self.session.flush()

        self._apply_totals(invoice, computed)
        self._write_lines(invoice, computed)
        invoice.discount_reason = discount_reason
        invoice.pricing_notes = pricing_notes or None
        invoice.amended_at = _now()
        invoice.amendment_reason = reason.strip()
        invoice.amendment_count += 1
        invoice.status = self._status_for(invoice)
        await self.session.flush()
        logger.info(
            "invoice_amended",
            extra={"invoice": invoice.invoice_number, "total_paise": invoice.total_paise,
                   "amendment": invoice.amendment_count},
        )
        return invoice

    async def cancel_visit(
        self, visit_id: uuid.UUID, *, reason: str
    ) -> Visit:
        """Cancel a registration.

        Every bill against it has to be cancelled first. Doing it the other
        way round — cancelling the registration and cascading down — would
        cancel bills the counter never looked at, including ones somebody has
        paid.
        """
        if not (reason or "").strip():
            raise ReceptionError("Cancelling a registration needs a reason.")

        visit = await self.session.scalar(
            select(Visit).where(Visit.id == visit_id).with_for_update()
        )
        if visit is None:
            raise ReceptionError("Registration not found.")
        if visit.status is VisitStatus.CANCELLED:
            raise ReceptionError("This registration is already cancelled.")

        result = await self.session.execute(
            select(Invoice).where(
                Invoice.visit_id == visit_id,
                Invoice.status != InvoiceStatus.CANCELLED,
            )
        )
        live = list(result.scalars())
        if live:
            numbers = ", ".join(invoice.invoice_number for invoice in live[:3])
            more = "" if len(live) <= 3 else f" and {len(live) - 3} more"
            raise ReceptionError(
                f"Cancel the bills against this registration first: {numbers}{more}."
            )

        visit.status = VisitStatus.CANCELLED
        visit.cancelled_at = _now()
        visit.cancellation_reason = reason.strip()
        await self.session.flush()
        return visit

    async def uncancel_visit(self, visit_id: uuid.UUID) -> Visit:
        """Reinstate a registration cancelled by mistake.

        It comes back as registered rather than as whatever it was before.
        A patient who was mid-consultation when their registration was
        cancelled is not mid-consultation now, and putting them back on the
        board in that state would have the doctor called to an empty room.
        """
        visit = await self.session.scalar(
            select(Visit).where(Visit.id == visit_id).with_for_update()
        )
        if visit is None:
            raise ReceptionError("Registration not found.")
        if visit.status is not VisitStatus.CANCELLED:
            raise ReceptionError("This registration is not cancelled.")

        visit.status = VisitStatus.REGISTERED
        visit.cancelled_at = None
        visit.cancellation_reason = None
        await self.session.flush()
        return visit

    async def open_cash_session(
        self, *, cashier_id: Optional[uuid.UUID], cashier_name: str,
        counter_name: str = "Reception", opening_float_paise: int = 0,
    ) -> CashSession:
        result = await self.session.execute(
            select(CashSession).where(
                and_(
                    CashSession.cashier_id == cashier_id,
                    CashSession.status == CashSessionStatus.OPEN,
                )
            )
        )
        if result.scalar_one_or_none() is not None:
            raise ReceptionError(
                "This cashier already has an open session. Close it before opening another."
            )
        session_row = CashSession(
            counter_name=counter_name,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            status=CashSessionStatus.OPEN,
            opened_at=_now(),
            opening_float_paise=opening_float_paise,
        )
        self.session.add(session_row)
        await self.session.flush()
        return session_row

    async def close_cash_session(
        self, cash_session_id: uuid.UUID, *, counted_cash_paise: int,
        variance_note: Optional[str] = None,
        cashier_id: Optional[uuid.UUID] = None,
    ) -> Tuple[CashSession, Dict[str, int]]:
        """Close a shift and reconcile the drawer.

        Only cash is counted: card and UPI settle through the bank and are
        reconciled against statements, not against the drawer.
        """
        session_row = await self.session.get(CashSession, cash_session_id)
        if session_row is None:
            raise ReceptionError("Cash session not found.")
        if session_row.status is not CashSessionStatus.OPEN:
            raise ReceptionError("This session is already closed.")
        if cashier_id is not None and session_row.cashier_id != cashier_id:
            raise ReceptionError("You can only close your own cash session.")

        result = await self.session.execute(
            select(Payment.mode, func.sum(Payment.amount_paise))
            .where(Payment.cash_session_id == cash_session_id)
            .group_by(Payment.mode)
        )
        by_mode = {mode.value: int(amount or 0) for mode, amount in result.all()}
        cash_taken = by_mode.get(PaymentMode.CASH.value, 0)
        expected = session_row.opening_float_paise + cash_taken

        session_row.counted_cash_paise = counted_cash_paise
        session_row.variance_paise = counted_cash_paise - expected
        session_row.variance_note = variance_note
        session_row.status = CashSessionStatus.CLOSED
        session_row.closed_at = _now()
        await self.session.flush()

        if session_row.variance_paise:
            logger.warning(
                "cash_session_variance",
                extra={"session": str(cash_session_id),
                       "variance_paise": session_row.variance_paise},
            )
        return session_row, {**by_mode, "expected_cash": expected}
