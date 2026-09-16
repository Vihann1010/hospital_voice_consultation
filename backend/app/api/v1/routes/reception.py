"""Reception counter: registration, visits, billing and collection."""
import uuid
from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.api.deps import (
    CurrentUser,
    get_diary_service,
    get_reception_service,
    require_permission,
)
from app.billing.engine import BillingError, compute_invoice
from app.billing.payment_modes import describe as describe_payment_modes
from app.billing.pricing import build_context as build_pricing_context
from app.billing.pdf import render_invoice_pdf
from app.billing.receipt_pdf import render_receipt_pdf
from app.core.audit import client_ip, record as audit_record
from app.core.permissions import Permission
from app.models.emr import CashSession, Payment, Visit, WalletEntry
from app.models.enums import (
    AuditAction,
    InvoiceStatus,
    CashSessionStatus,
    Department,
    PaymentMode,
    WalletEntryKind,
)
from app.models.patient import Patient
from app.printing.layout import load_layout
from app.schemas.emr_schemas import (
    AmendInvoiceRequest,
    CancelInvoiceRequest,
    InvoiceCreateRequest,
    InvoiceListOut,
    InvoiceOut,
    QuoteLineOut,
    QuoteOut,
    QuoteRequest,
    InvoiceSummaryOut,
    PatientCardOut,
    PatientDiaryOut,
    PatientRegisterRequest,
    PaymentOut,
    PaymentRequest,
    RefundRequest,
    RegisterAndBillRequest,
    RegisterAndBillResponse,
    VisitOpenRequest,
    VisitOut,
    WalletDepositRequest,
    WalletEntryOut,
    WalletOut,
    WalletPayRequest,
    WalletWithdrawRequest,
)
from app.services.diary_service import DiaryService
from app.services.reception_service import ReceptionError, ReceptionService

router = APIRouter(prefix="/reception", tags=["reception"])

Service = Annotated[ReceptionService, Depends(get_reception_service)]

# Guards name the permission required, not the roles that happen to hold it,
# so that these routes and /auth/me/permissions read from one catalogue and
# cannot come to disagree about who may do what.
READ_RECORDS = require_permission(Permission.PATIENT_READ)
REGISTER_PATIENT = require_permission(Permission.PATIENT_REGISTER)
OPEN_VISIT = require_permission(Permission.VISIT_CREATE)
RAISE_INVOICE = require_permission(Permission.INVOICE_CREATE)
READ_INVOICE = require_permission(Permission.INVOICE_READ)
COLLECT_PAYMENT = require_permission(Permission.PAYMENT_COLLECT)
# Registering, billing and collecting in one transaction needs all three, so
# a role holding only part of the counter's work cannot half-complete it.
COUNTER_SALE = require_permission(
    Permission.PATIENT_REGISTER,
    Permission.VISIT_CREATE,
    Permission.INVOICE_CREATE,
    Permission.PAYMENT_COLLECT,
)
# Money leaving the till, and unpicking a raised bill, are not counter work.
ISSUE_REFUND = require_permission(Permission.REFUND_ISSUE)
CANCEL_INVOICE = require_permission(Permission.INVOICE_CANCEL)


@router.get("/patients/search", response_model=List[PatientCardOut],
            dependencies=[Depends(READ_RECORDS)])
async def search_patients(
    service: Service,
    q: str = Query(..., min_length=1, max_length=120,
                   description="UHID, phone number or name"),
) -> List[PatientCardOut]:
    """Find a returning patient. An exact UHID match wins outright."""
    found = await service.find_patients(q)
    return [PatientCardOut.model_validate(patient) for patient in found]


@router.post("/patients", response_model=PatientCardOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(REGISTER_PATIENT)])
async def register_patient(
    payload: PatientRegisterRequest, service: Service, user: CurrentUser
) -> PatientCardOut:
    """Register a new patient and issue their permanent UHID."""
    try:
        patient = await service.register_patient(**payload.model_dump())
        await service.session.commit()
    except ReceptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return PatientCardOut.model_validate(patient)


@router.post("/register-and-bill", response_model=RegisterAndBillResponse,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(COUNTER_SALE)])
async def register_and_bill(
    payload: RegisterAndBillRequest, service: Service, user: CurrentUser,
    request: Request,
) -> RegisterAndBillResponse:
    """The counter workflow in one transaction.

    Registration, visit, invoice and (optionally) payment either all succeed
    or none do. A patient with a visit but no bill, or a bill with no payment
    recorded, is precisely the inconsistency that has to be reconciled by hand
    at the end of the day.
    """
    try:
        if payload.patient_id is not None:
            patient = await service.session.get(Patient, payload.patient_id)
            if patient is None:
                raise ReceptionError("Patient not found.")
        elif payload.new_patient is not None:
            patient = await service.register_patient(**payload.new_patient.model_dump())
        else:
            raise ReceptionError(
                "Provide an existing patient, or the details to register a new one."
            )

        visit = await service.open_visit(
            patient_id=patient.id,
            department=payload.department,
            doctor_id=payload.doctor_id,
            doctor_name=payload.doctor_name,
            visit_type=payload.visit_type,
            payer_type=payload.payer_type,
            referred_by=payload.referred_by,
            registered_by_name=user.full_name,
        )

        invoice = await service.create_invoice(
            visit_id=visit.id,
            patient_id=patient.id,
            items=[item.model_dump() for item in payload.items],
            invoice_discount_paise=payload.invoice_discount_paise,
            discount_reason=payload.discount_reason,
            discount_approved_by=user.full_name if payload.invoice_discount_paise else None,
            payer_type=payload.payer_type,
            doctor_name=payload.doctor_name,
            organisation_id=payload.organisation_id,
            created_by_name=user.full_name,
            issue=True,
        )

        payment = None
        if payload.payment is not None:
            cash_session_id = None
            if payload.payment.mode is PaymentMode.CASH:
                cash_session = await service.session.scalar(
                    select(CashSession).where(
                        CashSession.cashier_id == user.id,
                        CashSession.status == CashSessionStatus.OPEN,
                    )
                )
                cash_session_id = cash_session.id if cash_session else None
            payment = await service.record_payment(
                invoice_id=invoice.id,
                amount_paise=payload.payment.amount_paise,
                mode=payload.payment.mode,
                reference=payload.payment.reference,
                received_by_id=user.id,
                received_by_name=user.full_name,
                cash_session_id=cash_session_id,
            )

        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    invoice = await service.get_invoice(invoice.id)
    await audit_record(
        AuditAction.CREATE_ORDER,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="invoice", entity_id=invoice.id, patient_id=patient.id,
        ip_address=client_ip(request),
        detail={"invoice": invoice.invoice_number, "visit": visit.visit_number,
                "total_paise": invoice.total_paise},
    )
    return RegisterAndBillResponse(
        patient=PatientCardOut.model_validate(patient),
        visit=VisitOut.model_validate(visit),
        invoice=InvoiceOut.model_validate(invoice),
        payment=PaymentOut.model_validate(payment) if payment else None,
    )


@router.post("/visits", response_model=VisitOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(OPEN_VISIT)])
async def open_visit(
    payload: VisitOpenRequest, service: Service, user: CurrentUser
) -> VisitOut:
    try:
        visit = await service.open_visit(
            **payload.model_dump(), registered_by_name=user.full_name
        )
        await service.session.commit()
    except ReceptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return VisitOut.model_validate(visit)


@router.get("/visits/today", response_model=List[VisitOut],
            dependencies=[Depends(READ_RECORDS)])
async def todays_visits(
    service: Service,
    department: Optional[Department] = Query(default=None),
    on: Optional[date] = Query(default=None),
) -> List[VisitOut]:
    visits = await service.todays_visits(department=department, on=on)
    return [VisitOut.model_validate(visit) for visit in visits]


@router.get("/intake-queue", dependencies=[Depends(READ_RECORDS)])
async def intake_queue(
    service: Service,
    department: Optional[Department] = Query(default=None),
) -> dict:
    """Registered patients waiting to start voice intake.

    Read by the intake terminal so the patient is picked up from the counter's
    record instead of being asked for their details again.
    """
    waiting = await service.intake_queue(department=department)
    return {"count": len(waiting), "patients": waiting}


@router.post("/visits/{visit_id}/consultation/{consultation_id}",
             response_model=VisitOut, dependencies=[Depends(OPEN_VISIT)])
async def attach_consultation(
    visit_id: uuid.UUID, consultation_id: uuid.UUID, service: Service
) -> VisitOut:
    """Link the voice consultation that was started for this visit."""
    visit = await service.attach_consultation(visit_id, consultation_id)
    if visit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit not found")
    await service.session.commit()
    return VisitOut.model_validate(visit)


@router.post("/invoices", response_model=InvoiceOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(RAISE_INVOICE)])
async def create_invoice(
    payload: InvoiceCreateRequest, service: Service, user: CurrentUser
) -> InvoiceOut:
    try:
        invoice = await service.create_invoice(
            visit_id=payload.visit_id,
            patient_id=payload.patient_id,
            items=[item.model_dump() for item in payload.items],
            invoice_discount_paise=payload.invoice_discount_paise,
            discount_reason=payload.discount_reason,
            discount_approved_by=user.full_name if payload.invoice_discount_paise else None,
            payer_type=payload.payer_type,
            payer_covered_paise=payload.payer_covered_paise,
            consultant_id=payload.consultant_id,
            doctor_name=payload.doctor_name,
            organisation_id=payload.organisation_id,
            created_by_name=user.full_name,
            issue=payload.issue,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceOut.model_validate(await service.get_invoice(invoice.id))


@router.get("/patients/{patient_id}/diary", response_model=PatientDiaryOut,
            dependencies=[Depends(READ_INVOICE)])
async def patient_diary(
    patient_id: uuid.UUID,
    diary: Annotated[DiaryService, Depends(get_diary_service)],
) -> PatientDiaryOut:
    """Everything this patient has been charged and has paid, in one list.

    OPD bills, inpatient stays and counter advances together, with a running
    balance. The question it answers - "what does this patient owe" - used to
    need three screens and mental arithmetic.
    """
    found = await diary.for_patient(patient_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    return PatientDiaryOut(**found)


@router.post("/quote", response_model=QuoteOut, dependencies=[Depends(RAISE_INVOICE)])
async def quote(payload: QuoteRequest, service: Service) -> QuoteOut:
    """What this bill would come to, and why.

    Read by the counter as the clerk builds the bill, so a free follow-up
    appears on screen before the patient is asked for money rather than as a
    surprise zero on the printed bill. Nothing is written.

    It shares `_price_items` with the real thing, which is the point: a quote
    that could disagree with the bill would be worse than no quote.
    """
    try:
        context = await build_pricing_context(
            service.session,
            patient_id=payload.patient_id,
            consultant_id=payload.consultant_id,
            doctor_name=payload.doctor_name,
            organisation_id=payload.organisation_id,
        )
        lines, notes = await service._price_items(
            [item.model_dump() for item in payload.items], context=context
        )
        computed = compute_invoice(
            lines, invoice_discount_paise=payload.invoice_discount_paise
        )
    except (ReceptionError, BillingError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return QuoteOut(
        gross_paise=computed.gross_paise,
        discount_paise=computed.discount_paise,
        taxable_paise=computed.taxable_paise,
        tax_paise=computed.cgst_paise + computed.sgst_paise + computed.igst_paise,
        total_paise=computed.total_paise,
        notes=notes,
        lines=[
            QuoteLineOut(
                description=line.description,
                code=line.code,
                remark=line.remark,
                quantity=line.quantity,
                unit_rate_paise=line.unit_rate_paise,
                discount_paise=line.discount_paise,
                total_paise=line.total_paise,
            )
            for line in computed.lines
        ],
    )


@router.get("/invoices", response_model=InvoiceListOut,
            dependencies=[Depends(READ_INVOICE)])
async def list_invoices(
    service: Service,
    q: Optional[str] = Query(default=None, max_length=120,
                             description="Invoice number, UHID, name or phone"),
    patient_id: Optional[uuid.UUID] = Query(default=None),
    invoice_status: Optional[InvoiceStatus] = Query(default=None, alias="status"),
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> InvoiceListOut:
    """Look up a past bill, to reprint it or to correct it."""
    total, rows = await service.find_invoices(
        q=q, patient_id=patient_id, status=invoice_status,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )
    return InvoiceListOut(
        total=total, items=[InvoiceSummaryOut(**row) for row in rows]
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut,
            dependencies=[Depends(READ_INVOICE)])
async def get_invoice(invoice_id: uuid.UUID, service: Service) -> InvoiceOut:
    invoice = await service.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return InvoiceOut.model_validate(invoice)


@router.get("/invoices/{invoice_id}/pdf", dependencies=[Depends(READ_INVOICE)])
async def invoice_pdf(
    invoice_id: uuid.UUID,
    service: Service,
    duplicate: bool = Query(
        default=False,
        description="Stamp the copy DUPLICATE. Set on any reprint of a bill "
                    "the patient has already been handed.",
    ),
) -> Response:
    invoice = await service.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    patient = await service.session.get(Patient, invoice.patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    visit_number = None
    if invoice.visit_id:
        visit = await service.session.get(Visit, invoice.visit_id)
        visit_number = visit.visit_number if visit else None
    pdf = render_invoice_pdf(
        invoice, patient, visit_number,
        watermark="DUPLICATE" if duplicate else None,
        layout=await load_layout(service.session, "invoice"),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice.invoice_number}.pdf"',
        },
    )


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(COLLECT_PAYMENT)])
async def record_payment(
    invoice_id: uuid.UUID, payload: PaymentRequest, service: Service, user: CurrentUser
) -> PaymentOut:
    try:
        payment = await service.record_payment(
            invoice_id=invoice_id,
            amount_paise=payload.amount_paise,
            mode=payload.mode,
            reference=payload.reference,
            mode_details=payload.mode_details,
            received_by_id=user.id,
            received_by_name=user.full_name,
            cash_session_id=payload.cash_session_id,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return PaymentOut.model_validate(payment)


@router.post("/invoices/{invoice_id}/refund", response_model=PaymentOut,
             dependencies=[Depends(ISSUE_REFUND)])
async def refund(
    invoice_id: uuid.UUID, payload: RefundRequest, service: Service,
    user: CurrentUser, request: Request,
) -> PaymentOut:
    """Return money to a patient. Supervisor only, and always audited."""
    try:
        payment = await service.refund(
            invoice_id=invoice_id, amount_paise=payload.amount_paise,
            reason=payload.reason, mode=payload.mode, to_wallet=payload.to_wallet,
            received_by_name=user.full_name,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.REFUND_ISSUE,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="refund", entity_id=payment.id,
        ip_address=client_ip(request),
        detail={"receipt": payment.receipt_number,
                "amount_paise": payload.amount_paise, "reason": payload.reason,
                "destination": "wallet" if payload.to_wallet else payload.mode.value},
    )
    return PaymentOut.model_validate(payment)


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceOut,
             dependencies=[Depends(CANCEL_INVOICE)])
async def cancel_invoice(
    invoice_id: uuid.UUID, payload: CancelInvoiceRequest, service: Service,
    user: CurrentUser, request: Request,
) -> InvoiceOut:
    try:
        invoice = await service.cancel_invoice(invoice_id, reason=payload.reason)
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.INVOICE_CANCEL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="invoice_cancellation", entity_id=invoice.id,
        ip_address=client_ip(request),
        detail={"invoice": invoice.invoice_number, "reason": payload.reason},
    )
    return InvoiceOut.model_validate(await service.get_invoice(invoice.id))


# ------------------------------------------------------------------ wallet
@router.get("/patients/{patient_id}/wallet", response_model=WalletOut,
            dependencies=[Depends(READ_INVOICE)])
async def patient_wallet(
    patient_id: uuid.UUID, service: Service,
    limit: int = Query(default=50, ge=1, le=500),
) -> WalletOut:
    """A patient's credit and how it got there."""
    balance, entries = await service.wallet_statement(patient_id, limit=limit)
    return WalletOut(
        patient_id=patient_id,
        balance_paise=balance,
        entries=[WalletEntryOut.model_validate(entry) for entry in entries],
    )


@router.post("/patients/{patient_id}/wallet/deposit", response_model=WalletEntryOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(COLLECT_PAYMENT)])
async def wallet_deposit(
    patient_id: uuid.UUID, payload: WalletDepositRequest, service: Service,
    user: CurrentUser, request: Request,
) -> WalletEntryOut:
    """Take an advance onto the patient's account.

    Counter work, like any other collection — the money is arriving, not
    leaving. Paying it back out is a different permission entirely.
    """
    try:
        entry = await service.wallet_deposit(
            patient_id=patient_id,
            amount_paise=payload.amount_paise,
            mode=payload.mode,
            mode_details=payload.mode_details,
            reason=payload.reason,
            received_by_name=user.full_name,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.WALLET_DEPOSIT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="wallet_entry", entity_id=entry.id, patient_id=patient_id,
        ip_address=client_ip(request),
        detail={"receipt": entry.receipt_number, "amount_paise": payload.amount_paise,
                "balance_paise": entry.balance_after_paise, "mode": payload.mode.value},
    )
    return WalletEntryOut.model_validate(entry)


@router.post("/patients/{patient_id}/wallet/withdraw", response_model=WalletEntryOut,
             dependencies=[Depends(ISSUE_REFUND)])
async def wallet_withdraw(
    patient_id: uuid.UUID, payload: WalletWithdrawRequest, service: Service,
    user: CurrentUser, request: Request,
) -> WalletEntryOut:
    """Hand a balance back to the patient.

    Money leaving the hospital, so it needs the same authority as a refund
    rather than the authority to take payment.
    """
    try:
        entry = await service.wallet_withdraw(
            patient_id=patient_id,
            amount_paise=payload.amount_paise,
            reason=payload.reason,
            received_by_name=user.full_name,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.WALLET_WITHDRAWAL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="wallet_entry", entity_id=entry.id, patient_id=patient_id,
        ip_address=client_ip(request),
        detail={"receipt": entry.receipt_number, "amount_paise": payload.amount_paise,
                "balance_paise": entry.balance_after_paise, "reason": payload.reason},
    )
    return WalletEntryOut.model_validate(entry)


@router.post("/invoices/{invoice_id}/pay-from-wallet", response_model=PaymentOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(COLLECT_PAYMENT)])
async def pay_from_wallet(
    invoice_id: uuid.UUID, payload: WalletPayRequest, service: Service,
    user: CurrentUser,
) -> PaymentOut:
    """Settle a bill from credit the patient already left with the hospital."""
    try:
        payment = await service.pay_from_wallet(
            invoice_id=invoice_id,
            amount_paise=payload.amount_paise,
            received_by_id=user.id,
            received_by_name=user.full_name,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return PaymentOut.model_validate(payment)


@router.get("/payment-modes", dependencies=[Depends(READ_RECORDS)])
async def payment_modes() -> dict:
    """What each mode requires, so the counter renders the right fields.

    Served rather than duplicated in the front end: a cheque that needs a
    bank name here and not there is a bug nobody finds until an auditor
    cannot trace a payment.
    """
    return {"modes": describe_payment_modes()}


@router.get("/receipts/{payment_id}/pdf", dependencies=[Depends(READ_INVOICE)])
async def receipt_pdf(
    payment_id: uuid.UUID, service: Service,
    duplicate: bool = Query(default=False),
) -> Response:
    """Print or reprint the receipt for one payment or refund."""
    payment = await service.session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")
    invoice = await service.get_invoice(payment.invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found")
    patient = await service.session.get(Patient, invoice.patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")

    pdf = render_receipt_pdf(
        patient=patient,
        receipt_number=payment.receipt_number,
        amount_paise=payment.amount_paise,
        mode=payment.mode,
        mode_details=payment.mode_details,
        received_at=payment.received_at,
        received_by_name=payment.received_by_name,
        invoice=invoice,
        is_refund=payment.is_refund,
        reason=payment.refund_reason,
        purpose="Refund issued" if payment.is_refund else "Payment received",
        layout=await load_layout(service.session, "receipt"),
        watermark="DUPLICATE" if duplicate else None,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{payment.receipt_number}.pdf"',
        },
    )


@router.get("/wallet-entries/{entry_id}/pdf", dependencies=[Depends(READ_INVOICE)])
async def wallet_receipt_pdf(
    entry_id: uuid.UUID, service: Service,
    duplicate: bool = Query(default=False),
) -> Response:
    """The receipt for a deposit or a withdrawal.

    A separate route because these movements have no invoice behind them —
    which is precisely why they needed a printable receipt in the first
    place.
    """
    entry = await service.session.get(WalletEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    if entry.kind not in (WalletEntryKind.DEPOSIT, WalletEntryKind.WITHDRAWAL):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only a deposit or a withdrawal has its own receipt; money applied to a "
            "bill is receipted against that bill.",
        )
    patient = await service.session.get(Patient, entry.patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")

    is_withdrawal = entry.kind is WalletEntryKind.WITHDRAWAL
    pdf = render_receipt_pdf(
        patient=patient,
        receipt_number=entry.receipt_number or "-",
        amount_paise=entry.amount_paise,
        mode=entry.mode or PaymentMode.CASH,
        received_at=entry.created_at,
        received_by_name=entry.created_by_name,
        purpose="Advance returned" if is_withdrawal else "Advance received",
        is_refund=is_withdrawal,
        reason=entry.reason,
        wallet_balance_paise=entry.balance_after_paise,
        layout=await load_layout(service.session, "receipt"),
        watermark="DUPLICATE" if duplicate else None,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{entry.receipt_number or entry.id}.pdf"',
        },
    )


# ------------------------------------------------------------- corrections
@router.post("/receipts/{payment_id}/cancel", response_model=PaymentOut,
             dependencies=[Depends(CANCEL_INVOICE)])
async def cancel_receipt(
    payment_id: uuid.UUID, payload: CancelInvoiceRequest, service: Service,
    user: CurrentUser, request: Request,
) -> PaymentOut:
    """Strike out a receipt entered by mistake.

    Not a refund: this says the entry was wrong and no money moved. Refused
    once the shift is closed and the drawer counted, because from that point
    the money is real whatever the receipt says.
    """
    try:
        payment = await service.cancel_receipt(
            payment_id, reason=payload.reason, cancelled_by_name=user.full_name
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.RECEIPT_CANCEL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="payment", entity_id=payment.id,
        ip_address=client_ip(request),
        detail={"receipt": payment.receipt_number,
                "amount_paise": payment.amount_paise, "reason": payload.reason},
    )
    return PaymentOut.model_validate(payment)


@router.post("/invoices/{invoice_id}/uncancel", response_model=InvoiceOut,
             dependencies=[Depends(CANCEL_INVOICE)])
async def uncancel_invoice(
    invoice_id: uuid.UUID, payload: CancelInvoiceRequest, service: Service,
    user: CurrentUser, request: Request,
) -> InvoiceOut:
    """Reinstate a bill cancelled by mistake.

    Its registration has to be live first — that ordering is the whole point
    of the cascade.
    """
    try:
        invoice = await service.uncancel_invoice(invoice_id, reason=payload.reason)
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.INVOICE_UNCANCEL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="invoice", entity_id=invoice.id, patient_id=invoice.patient_id,
        ip_address=client_ip(request),
        detail={"invoice": invoice.invoice_number, "reason": payload.reason},
    )
    return InvoiceOut.model_validate(await service.get_invoice(invoice.id))


@router.post("/invoices/{invoice_id}/amend", response_model=InvoiceOut,
             dependencies=[Depends(CANCEL_INVOICE)])
async def amend_invoice(
    invoice_id: uuid.UUID, payload: AmendInvoiceRequest, service: Service,
    user: CurrentUser, request: Request,
) -> InvoiceOut:
    """Correct a bill nobody has paid yet."""
    try:
        invoice = await service.amend_invoice(
            invoice_id=invoice_id,
            items=[item.model_dump() for item in payload.items],
            invoice_discount_paise=payload.invoice_discount_paise,
            discount_reason=payload.discount_reason,
            reason=payload.reason,
            amended_by_name=user.full_name,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.INVOICE_AMEND,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="invoice", entity_id=invoice.id, patient_id=invoice.patient_id,
        ip_address=client_ip(request),
        detail={"invoice": invoice.invoice_number, "reason": payload.reason,
                "total_paise": invoice.total_paise,
                "amendment": invoice.amendment_count},
    )
    return InvoiceOut.model_validate(await service.get_invoice(invoice.id))


@router.post("/visits/{visit_id}/cancel", response_model=VisitOut,
             dependencies=[Depends(CANCEL_INVOICE)])
async def cancel_visit(
    visit_id: uuid.UUID, payload: CancelInvoiceRequest, service: Service,
    user: CurrentUser, request: Request,
) -> VisitOut:
    """Cancel a registration. Its bills must be cancelled first."""
    try:
        visit = await service.cancel_visit(visit_id, reason=payload.reason)
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.VISIT_CANCEL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="visit", entity_id=visit.id, patient_id=visit.patient_id,
        ip_address=client_ip(request),
        detail={"visit": visit.visit_number, "reason": payload.reason},
    )
    return VisitOut.model_validate(visit)


@router.post("/visits/{visit_id}/uncancel", response_model=VisitOut,
             dependencies=[Depends(CANCEL_INVOICE)])
async def uncancel_visit(
    visit_id: uuid.UUID, service: Service, user: CurrentUser, request: Request,
) -> VisitOut:
    """Reinstate a registration, as registered rather than mid-consultation."""
    try:
        visit = await service.uncancel_visit(visit_id)
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.VISIT_UNCANCEL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="visit", entity_id=visit.id, patient_id=visit.patient_id,
        ip_address=client_ip(request),
        detail={"visit": visit.visit_number},
    )
    return VisitOut.model_validate(visit)
