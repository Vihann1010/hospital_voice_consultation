"""Reception counter: registration, visits, billing and collection."""
import uuid
from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, get_reception_service, require_roles
from app.core.audit import client_ip, record as audit_record
from app.models.enums import AuditAction, Department, UserRole
from app.models.patient import Patient
from app.schemas.emr_schemas import (
    CancelInvoiceRequest,
    InvoiceCreateRequest,
    InvoiceOut,
    PatientCardOut,
    PatientRegisterRequest,
    PaymentOut,
    PaymentRequest,
    RefundRequest,
    RegisterAndBillRequest,
    RegisterAndBillResponse,
    VisitOpenRequest,
    VisitOut,
)
from app.services.reception_service import ReceptionError, ReceptionService

router = APIRouter(prefix="/reception", tags=["reception"])

Service = Annotated[ReceptionService, Depends(get_reception_service)]
# Front desk work: staff do this all day, and it is not clinical authority.
DESK = require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.STAFF)
# Money that leaves the till needs a supervisor.
SUPERVISOR = require_roles(UserRole.ADMIN, UserRole.DOCTOR)


@router.get("/patients/search", response_model=List[PatientCardOut],
            dependencies=[Depends(DESK)])
async def search_patients(
    service: Service,
    q: str = Query(..., min_length=1, max_length=120,
                   description="UHID, phone number or name"),
) -> List[PatientCardOut]:
    """Find a returning patient. An exact UHID match wins outright."""
    found = await service.find_patients(q)
    return [PatientCardOut.model_validate(patient) for patient in found]


@router.post("/patients", response_model=PatientCardOut,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(DESK)])
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
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(DESK)])
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
            created_by_name=user.full_name,
            issue=True,
        )

        payment = None
        if payload.payment is not None:
            payment = await service.record_payment(
                invoice_id=invoice.id,
                amount_paise=payload.payment.amount_paise,
                mode=payload.payment.mode,
                reference=payload.payment.reference,
                received_by_id=user.id,
                received_by_name=user.full_name,
                cash_session_id=payload.payment.cash_session_id,
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
             dependencies=[Depends(DESK)])
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


@router.get("/visits/today", response_model=List[VisitOut], dependencies=[Depends(DESK)])
async def todays_visits(
    service: Service,
    department: Optional[Department] = Query(default=None),
    on: Optional[date] = Query(default=None),
) -> List[VisitOut]:
    visits = await service.todays_visits(department=department, on=on)
    return [VisitOut.model_validate(visit) for visit in visits]


@router.get("/intake-queue", dependencies=[Depends(DESK)])
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
             response_model=VisitOut, dependencies=[Depends(DESK)])
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
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(DESK)])
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
            created_by_name=user.full_name,
            issue=payload.issue,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceOut.model_validate(await service.get_invoice(invoice.id))


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut,
            dependencies=[Depends(DESK)])
async def get_invoice(invoice_id: uuid.UUID, service: Service) -> InvoiceOut:
    invoice = await service.get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return InvoiceOut.model_validate(invoice)


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentOut,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(DESK)])
async def record_payment(
    invoice_id: uuid.UUID, payload: PaymentRequest, service: Service, user: CurrentUser
) -> PaymentOut:
    try:
        payment = await service.record_payment(
            invoice_id=invoice_id,
            amount_paise=payload.amount_paise,
            mode=payload.mode,
            reference=payload.reference,
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
             dependencies=[Depends(SUPERVISOR)])
async def refund(
    invoice_id: uuid.UUID, payload: RefundRequest, service: Service,
    user: CurrentUser, request: Request,
) -> PaymentOut:
    """Return money to a patient. Supervisor only, and always audited."""
    try:
        payment = await service.refund(
            invoice_id=invoice_id, amount_paise=payload.amount_paise,
            reason=payload.reason, mode=payload.mode, received_by_name=user.full_name,
        )
        await service.session.commit()
    except ReceptionError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.EXPORT_DOCUMENT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="refund", entity_id=payment.id,
        ip_address=client_ip(request),
        detail={"receipt": payment.receipt_number,
                "amount_paise": payload.amount_paise, "reason": payload.reason},
    )
    return PaymentOut.model_validate(payment)


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceOut,
             dependencies=[Depends(SUPERVISOR)])
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
        AuditAction.EXPORT_DOCUMENT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="invoice_cancellation", entity_id=invoice.id,
        ip_address=client_ip(request),
        detail={"invoice": invoice.invoice_number, "reason": payload.reason},
    )
    return InvoiceOut.model_validate(await service.get_invoice(invoice.id))
