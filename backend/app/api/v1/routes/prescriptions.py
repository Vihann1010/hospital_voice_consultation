import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, get_prescription_service, require_roles
from app.core.audit import client_ip, record as audit_record
from app.messaging.factory import get_provider
from app.models.enums import AuditAction, Department, UserRole
from app.prescriptions import formulary
from app.prescriptions.pdf import pdf_capabilities
from app.prescriptions.safety import blocking_alerts, run_all
from app.schemas.prescription_schemas import (
    DeliveryOut,
    DictationRequest,
    DictationResponse,
    FormularyOut,
    MedicineOut,
    PrescriptionCreateRequest,
    PrescriptionListOut,
    PrescriptionOut,
    SafetyCheckRequest,
    SafetyCheckResponse,
    SendWhatsAppRequest,
)
from app.services.prescription_service import PrescriptionError, PrescriptionService

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])

Service = Annotated[PrescriptionService, Depends(get_prescription_service)]
STAFF = require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.STAFF)
CLINICIAN = require_roles(UserRole.ADMIN, UserRole.DOCTOR)


def _medicine_out(item) -> MedicineOut:
    return MedicineOut(
        code=item.code, name=item.name, ingredients=item.ingredients, form=item.form,
        strengths=item.strengths, default_frequency=item.default_frequency,
        default_duration=item.default_duration, default_timing=item.default_timing,
        category=item.category, note=item.note,
    )


@router.get("/formulary", response_model=FormularyOut, dependencies=[Depends(STAFF)])
async def search_formulary(
    q: Optional[str] = Query(default=None, max_length=120),
    department: Optional[Department] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
) -> FormularyOut:
    """Medicine autocomplete and search."""
    results = formulary.search(q, department=department, limit=limit)
    return FormularyOut(items=[_medicine_out(item) for item in results], total=len(results))


@router.get("/capabilities", dependencies=[Depends(STAFF)])
async def capabilities() -> dict:
    """What this node can do — PDF, QR and which messaging provider is live."""
    return {**pdf_capabilities(), "messaging_provider": get_provider().name}


@router.post("/dictation", response_model=DictationResponse, dependencies=[Depends(CLINICIAN)])
async def parse_dictation(payload: DictationRequest, service: Service) -> DictationResponse:
    """Turn dictated speech into structured, editable medicine rows.

    Nothing is prescribed here: the rows populate a form the doctor must review.
    """
    medicines = service.parse_dictation_text(payload.transcript)
    alerts: List[dict] = []
    if payload.patient_id is not None and medicines:
        alerts = await service.run_safety(payload.patient_id, medicines)
    return DictationResponse(
        medicines=medicines, alerts=alerts, transcript=payload.transcript
    )


@router.post("/safety-check", response_model=SafetyCheckResponse,
             dependencies=[Depends(CLINICIAN)])
async def safety_check(payload: SafetyCheckRequest, service: Service) -> SafetyCheckResponse:
    """Re-run every deterministic check. Called on each edit of the medicine list."""
    alerts = await service.run_safety(payload.patient_id, payload.medicines)
    allergies = await service._known_allergies(payload.patient_id)
    blocking = sum(1 for alert in alerts if alert.get("severity") == "serious")
    return SafetyCheckResponse(alerts=alerts, blocking=blocking, known_allergies=allergies)


@router.get("/prefill", dependencies=[Depends(CLINICIAN)])
async def prescription_prefill(
    service: Service,
    consultation_id: uuid.UUID = Query(..., description="Consultation to draw from"),
) -> dict:
    """Clinical fields for a new prescription, composed from the AI dossier.

    Diagnosis, cause, complaint, findings, investigations and advice are all
    filled in from what the intake pipeline already produced. Medicines are not
    included — drug choice stays with the prescriber.
    """
    return await service.prefill_from_consultation(consultation_id)


@router.post("", response_model=PrescriptionOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(CLINICIAN)])
async def create_prescription(
    payload: PrescriptionCreateRequest, service: Service, user: CurrentUser
) -> PrescriptionOut:
    try:
        prescription = await service.create(
            patient_id=payload.patient_id,
            consultation_id=payload.consultation_id,
            department=user.department or Department.ORTHOPEDICS,
            doctor_id=user.id,
            doctor_name=user.full_name,
            doctor_qualification=getattr(user, "qualification", None),
            doctor_registration=getattr(user, "registration_number", None),
            medicines=[medicine.model_dump() for medicine in payload.medicines],
            diagnosis=payload.diagnosis,
            cause=payload.cause,
            chief_complaint=payload.chief_complaint,
            clinical_findings=payload.clinical_findings,
            investigations=payload.investigations,
            general_instructions=payload.general_instructions,
            follow_up_notes=payload.follow_up_notes,
            follow_up_date=payload.follow_up_date,
            dictation_transcript=payload.dictation_transcript,
            acknowledged_alerts=payload.acknowledged_alerts,
            issue=payload.issue,
        )
    except PrescriptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await audit_record(
        AuditAction.CREATE_PRESCRIPTION,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="prescription", entity_id=prescription.id,
        patient_id=prescription.patient_id,
        detail={"number": prescription.prescription_number,
                "medicines": len(prescription.medicines)},
    )
    return PrescriptionOut.model_validate(prescription)


@router.get("", response_model=PrescriptionListOut, dependencies=[Depends(STAFF)])
async def list_prescriptions(
    service: Service,
    patient_id: Optional[uuid.UUID] = Query(default=None),
    consultation_id: Optional[uuid.UUID] = Query(default=None),
) -> PrescriptionListOut:
    if patient_id is None and consultation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Provide patient_id or consultation_id")
    items = await service.list_for(patient_id=patient_id, consultation_id=consultation_id)
    return PrescriptionListOut(
        items=[PrescriptionOut.model_validate(item) for item in items], total=len(items)
    )


@router.get("/{prescription_id}", response_model=PrescriptionOut, dependencies=[Depends(STAFF)])
async def get_prescription(prescription_id: uuid.UUID, service: Service) -> PrescriptionOut:
    prescription = await service.get(prescription_id)
    if prescription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
    return PrescriptionOut.model_validate(prescription)


@router.get("/{prescription_id}/pdf", dependencies=[Depends(STAFF)])
async def download_pdf(prescription_id: uuid.UUID, service: Service) -> FileResponse:
    found = await service.pdf_bytes(prescription_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No PDF has been generated for this prescription")
    path, filename = found
    return FileResponse(path, media_type="application/pdf", filename=filename,
                        headers={"Cache-Control": "private, max-age=600"})


@router.post("/{prescription_id}/pdf", response_model=PrescriptionOut,
             dependencies=[Depends(CLINICIAN)])
async def regenerate_pdf(prescription_id: uuid.UUID, service: Service) -> PrescriptionOut:
    try:
        prescription = await service.generate_pdf(prescription_id)
    except PrescriptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if prescription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
    return PrescriptionOut.model_validate(prescription)


@router.post("/{prescription_id}/send/whatsapp", response_model=DeliveryOut,
             dependencies=[Depends(CLINICIAN)])
async def send_whatsapp(
    prescription_id: uuid.UUID, payload: SendWhatsAppRequest, service: Service,
    user: CurrentUser,
) -> DeliveryOut:
    """Send the PDF to the patient's registered WhatsApp number."""
    try:
        delivery = await service.send_to_whatsapp(
            prescription_id, requested_by_name=user.full_name,
            override_number=payload.phone_number,
        )
    except PrescriptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await audit_record(
        AuditAction.SEND_PRESCRIPTION,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="prescription", entity_id=prescription_id,
        success=delivery.status.value != "failed",
        detail={"recipient": delivery.recipient, "provider": delivery.provider,
                "status": delivery.status.value},
    )
    return DeliveryOut.model_validate(delivery)


@router.get("/{prescription_id}/deliveries", response_model=List[DeliveryOut],
            dependencies=[Depends(STAFF)])
async def delivery_history(prescription_id: uuid.UUID, service: Service) -> List[DeliveryOut]:
    deliveries = await service.deliveries.for_prescription(prescription_id)
    return [DeliveryOut.model_validate(delivery) for delivery in deliveries]


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryOut,
             dependencies=[Depends(CLINICIAN)])
async def retry_delivery(delivery_id: uuid.UUID, service: Service) -> DeliveryOut:
    try:
        delivery = await service.retry_delivery(delivery_id)
    except PrescriptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
    return DeliveryOut.model_validate(delivery)


@router.post("/{prescription_id}/cancel", response_model=PrescriptionOut,
             dependencies=[Depends(CLINICIAN)])
async def cancel_prescription(prescription_id: uuid.UUID, service: Service) -> PrescriptionOut:
    prescription = await service.cancel(prescription_id)
    if prescription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
    return PrescriptionOut.model_validate(prescription)
