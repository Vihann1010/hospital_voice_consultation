import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, get_patient_service, require_roles
from app.api.scoping import effective_department
from app.models.enums import UserRole
from app.schemas.schemas import (
    PatientHistoryOut,
    PatientListItemOut,
    PatientListOut,
    PatientOut,
    PatientVisitOut,
)
from app.services.patient_service import PatientService

router = APIRouter(prefix="/patients", tags=["patients"])

Service = Annotated[PatientService, Depends(get_patient_service)]
STAFF = require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.STAFF)


@router.get("", response_model=PatientListOut, dependencies=[Depends(STAFF)])
async def search_patients(
    service: Service,
    user: CurrentUser,
    q: Optional[str] = Query(default=None, max_length=120, description="Name or phone number"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
) -> PatientListOut:
    # A consultant only sees patients who have attended their department.
    patients, total, counts = await service.search(
        query=q, offset=offset, limit=limit,
        department=effective_department(user),
    )
    items = []
    for patient in patients:
        item = PatientListItemOut.model_validate(patient)
        summary = counts.get(patient.id, {})
        item.visit_count = summary.get("visit_count", 0)
        item.visit_reason = summary.get("visit_reason")
        item.payment_status = summary.get("payment_status")
        items.append(item)
    return PatientListOut(items=items, total=total)


@router.get("/{patient_id}", response_model=PatientHistoryOut, dependencies=[Depends(STAFF)])
async def get_patient_history(
    patient_id: uuid.UUID, service: Service, user: CurrentUser
) -> PatientHistoryOut:
    """Longitudinal view: standing medicines, allergies, conditions, and every visit."""
    patient = await service.get(patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    consultations = await service.history(
        patient_id, department=effective_department(user)
    )

    visits = []
    for consultation in consultations:
        dossier = consultation.medical_json or {}
        record = dossier.get("medical_json") or {}
        risk = dossier.get("risk_assessment") or {}
        summary = dossier.get("clinical_summary") or {}
        visits.append(
            PatientVisitOut(
                consultation_id=consultation.id,
                department=consultation.department,
                status=consultation.status,
                started_at=consultation.started_at,
                ended_at=consultation.ended_at,
                chief_complaint=record.get("chief_complaint"),
                overall_risk=risk.get("overall_risk"),
                one_liner=summary.get("one_liner"),
            )
        )

    return PatientHistoryOut(
        patient=PatientOut.model_validate(patient),
        summary=service.aggregate_history(consultations),
        visits=visits,
    )
