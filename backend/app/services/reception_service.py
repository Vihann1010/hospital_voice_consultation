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

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.billing.engine import (
    BillingError,
    LineInput,
    compute_invoice,
    validate_payment,
)
from app.billing.identifiers import (
    build_invoice_number,
    build_receipt_number,
    build_uhid,
    financial_year,
    normalise_uhid,
)
from app.core.logging import get_logger
from app.models.emr import (
    CashSession,
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
)
from app.models.patient import Patient

logger = get_logger(__name__)


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
        date_of_birth: Optional[date] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        blood_group: Optional[str] = None,
        emergency_contact_name: Optional[str] = None,
        emergency_contact_phone: Optional[str] = None,
    ) -> Patient:
        """Create a patient and issue their permanent UHID."""
        if not (name or "").strip():
            raise ReceptionError("The patient's name is required.")
        if age < 0 or age > 120:
            raise ReceptionError("Please check the age entered.")

        sequence = await self._next_sequence("uhid", "all")
        patient = Patient(
            uhid=build_uhid(sequence),
            name=name.strip(),
            age=age,
            gender=gender,
            phone_number=(phone_number or "").strip(),
            date_of_birth=date_of_birth,
            address=address,
            city=city,
            blood_group=blood_group,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
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

        today = date.today()
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
        created_by_name: str = "",
        issue: bool = True,
    ) -> Invoice:
        """Price the visit and raise the bill.

        Rates come from the tariff when a service is chosen by code, but the
        resolved values are written onto the invoice lines — the bill must not
        change if the tariff is revised next month.
        """
        lines: List[LineInput] = []
        for entry in items:
            service: Optional[ServiceItem] = None
            if entry.get("service_item_id"):
                service = await self.session.get(
                    ServiceItem, uuid.UUID(str(entry["service_item_id"]))
                )
            elif entry.get("code"):
                result = await self.session.execute(
                    select(ServiceItem).where(ServiceItem.code == entry["code"])
                )
                service = result.scalar_one_or_none()

            description = entry.get("description") or (service.name if service else "")
            if not description:
                raise ReceptionError("Every billed item needs a description.")

            rate = entry.get("unit_rate_paise")
            if rate is None:
                if service is None:
                    raise ReceptionError(f"No rate available for {description}.")
                rate = service.rate_paise

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
                )
            )

        try:
            computed = compute_invoice(
                lines, invoice_discount_paise=invoice_discount_paise
            )
        except BillingError as exc:
            raise ReceptionError(str(exc)) from exc

        today = date.today()
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
            issued_at=_now() if issue else None,
            created_by_name=created_by_name,
        )
        self.session.add(invoice)
        await self.session.flush()

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
        received_by_id: Optional[uuid.UUID] = None,
        received_by_name: str = "",
        cash_session_id: Optional[uuid.UUID] = None,
    ) -> Payment:
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

        today = date.today()
        sequence = await self._next_sequence("receipt", financial_year(today))
        payment = Payment(
            receipt_number=build_receipt_number(sequence, today),
            invoice_id=invoice_id,
            cash_session_id=cash_session_id,
            amount_paise=amount_paise,
            mode=mode,
            reference=reference,
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

    async def refund(
        self,
        *,
        invoice_id: uuid.UUID,
        amount_paise: int,
        reason: str,
        mode: PaymentMode = PaymentMode.CASH,
        received_by_name: str = "",
    ) -> Payment:
        """Return money as a negative payment rather than by deleting one.

        The original receipt stays in the record, so what was taken and what
        was given back are both auditable.
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

        today = date.today()
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
            select(Visit)
            .where(Visit.visit_date == (on or date.today()))
            .order_by(Visit.token_number)
        )
        if department is not None:
            statement = statement.where(Visit.department == department)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

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
        day = on or date.today()
        statement = (
            select(Visit, Patient)
            .join(Patient, Patient.id == Visit.patient_id)
            .where(
                Visit.visit_date == day,
                Visit.status == VisitStatus.REGISTERED,
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
