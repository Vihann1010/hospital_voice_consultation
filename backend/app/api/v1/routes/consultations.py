import asyncio
import uuid
from typing import Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from fastapi.responses import FileResponse

from app.core.audit import client_ip, record as audit_record
from app.api.deps import CurrentUser, get_consultation_service, get_copilot_service, require_permission
from app.core.permissions import Permission
from app.api.scoping import assert_may_access, effective_department
from app.core.security import TOKEN_TYPE_CONSULTATION, decode_token
from app.models.enums import AuditAction, ConsultationStatus, Department, VisitType
from app.schemas.schemas import (
    ConsultationDetailOut,
    ConsultationListItemOut,
    ConsultationListOut,
    ConsultationStartFromVisitRequest,
    ConsultationStartRequest,
    ConsultationStartResponse,
    ConsultationStatsOut,
    CopilotDecisionOut,
    CopilotDecisionRequest,
)
from app.services.consultation_service import ConsultationError, ConsultationService
from app.services.copilot_service import CopilotService

router = APIRouter(prefix="/consultations", tags=["consultations"])

Service = Annotated[ConsultationService, Depends(get_consultation_service)]
Copilot = Annotated[CopilotService, Depends(get_copilot_service)]

READ_CONSULTATION = require_permission(Permission.CONSULTATION_READ)
CLINICIAN = require_permission(Permission.CONSULTATION_REVIEW)
USE_COPILOT = require_permission(Permission.COPILOT_USE)


class ConsultationRestartRequest(BaseModel):
    session_token: str


class ConsultationVitalsRequest(BaseModel):
    bpSys: Optional[str] = None
    bpDia: Optional[str] = None
    pulse: Optional[str] = None
    spo2: Optional[str] = None
    temperature: Optional[str] = None
    respiration: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    sugar: Optional[str] = None
    notes: Optional[str] = None


@router.post("/{consultation_id}/restart", response_model=ConsultationStartResponse)
async def restart_consultation(
    consultation_id: uuid.UUID,
    payload: ConsultationRestartRequest,
    service: Service,
) -> ConsultationStartResponse:
    claims = decode_token(payload.session_token)
    if (
        claims is None
        or claims.get("type") != TOKEN_TYPE_CONSULTATION
        or claims.get("consultation_id") != str(consultation_id)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid consultation session")
    try:
        response = await service.restart_from_consultation(consultation_id)
        await service.session.commit()
    except ConsultationError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return response


@router.post("/start-from-visit", response_model=ConsultationStartResponse,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(READ_CONSULTATION)])
async def start_from_visit(
    payload: ConsultationStartFromVisitRequest, service: Service
) -> ConsultationStartResponse:
    """Begin voice intake for a patient reception already registered.

    Staff-only, unlike the public /start: this trusts a visit that the counter
    created, so it must not be callable by anyone who can guess a visit id.
    """
    try:
        response = await service.start_from_visit(payload.visit_id)
        await service.session.commit()
    except ConsultationError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return response


@router.post("/start", response_model=ConsultationStartResponse, status_code=status.HTTP_201_CREATED)
async def start_consultation(
    payload: ConsultationStartRequest, service: Service
) -> ConsultationStartResponse:
    """Public patient intake: registers the patient and opens a voice session."""
    return await service.start(payload)


@router.get("/stats", response_model=ConsultationStatsOut, dependencies=[Depends(READ_CONSULTATION)])
async def consultation_stats(
    service: Service, user: CurrentUser,
    department: Optional[Department] = Query(default=None),
) -> ConsultationStatsOut:
    counts = await service.stats(department=effective_department(user, department))
    return ConsultationStatsOut(**counts)


@router.get("", response_model=ConsultationListOut, dependencies=[Depends(READ_CONSULTATION)])
async def list_consultations(
    service: Service,
    user: CurrentUser,
    department: Optional[Department] = Query(default=None),
    status_filter: Optional[ConsultationStatus] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, max_length=120),
    patient_id: Optional[uuid.UUID] = Query(default=None),
    reviewed: Optional[bool] = Query(default=None, description="Doctor sign-off state"),
    visit_type: Optional[VisitType] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> ConsultationListOut:
    items, total = await service.list(
        department=effective_department(user, department),
        status=status_filter,
        query=q,
        patient_id=patient_id,
        reviewed=reviewed,
        visit_type=visit_type,
        offset=offset,
        limit=limit,
    )
    rows = []
    for consultation in items:
        row = ConsultationListItemOut.model_validate(consultation)
        row.reviewed_at = (consultation.medical_json or {}).get("reviewed_at")
        rows.append(row)
    return ConsultationListOut(items=rows, total=total)


@router.get(
    "/{consultation_id}", response_model=ConsultationDetailOut, dependencies=[Depends(READ_CONSULTATION)]
)
async def get_consultation(
    consultation_id: uuid.UUID, service: Service, request: Request, user: CurrentUser
) -> ConsultationDetailOut:
    consultation = await service.get_detail(consultation_id)
    if consultation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
    # Opening a patient record is an auditable event.
    await audit_record(
        AuditAction.VIEW_CONSULTATION,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="consultation", entity_id=consultation_id,
        patient_id=consultation.patient_id,
        ip_address=client_ip(request), user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    assert_may_access(user, consultation.department)
    return ConsultationDetailOut.model_validate(consultation)


@router.post(
    "/{consultation_id}/vitals",
    response_model=ConsultationDetailOut,
    dependencies=[Depends(READ_CONSULTATION)],
)
async def update_consultation_vitals(
    consultation_id: uuid.UUID,
    payload: ConsultationVitalsRequest,
    service: Service,
    user: CurrentUser,
) -> ConsultationDetailOut:
    consultation = await service.update_vitals(consultation_id, payload.model_dump())
    if consultation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
    assert_may_access(user, consultation.department)
    await service.session.commit()
    return ConsultationDetailOut.model_validate(consultation)


@router.get("/{consultation_id}/copilot", dependencies=[Depends(USE_COPILOT)])
async def get_copilot_briefing(
    consultation_id: uuid.UUID,
    copilot: Copilot,
    refresh: bool = Query(default=False),
) -> dict:
    """AI decision support for the treating doctor. Advisory only."""
    briefing = await copilot.get_or_build(consultation_id, refresh=refresh)
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
    return briefing.model_dump()


@router.post(
    "/{consultation_id}/copilot/decisions",
    response_model=CopilotDecisionOut,
    dependencies=[Depends(CLINICIAN)],
)
async def record_copilot_decision(
    consultation_id: uuid.UUID,
    payload: CopilotDecisionRequest,
    copilot: Copilot,
    user: CurrentUser,
) -> CopilotDecisionOut:
    """Record the doctor's ruling on an AI suggestion. The clinician's decision
    is stored as a separate, attributable fact — the AI never overwrites it."""
    result = await copilot.record_decision(
        consultation_id,
        item_key=payload.item_key,
        decision=payload.decision,
        note=payload.note,
        doctor_id=user.id,
        doctor_name=user.full_name,
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
    return CopilotDecisionOut(item_key=payload.item_key, **result)


@router.post(
    "/{consultation_id}/review",
    response_model=ConsultationDetailOut,
    dependencies=[Depends(CLINICIAN)],
)
async def mark_reviewed(
    consultation_id: uuid.UUID, service: Service, user: CurrentUser
) -> ConsultationDetailOut:
    """Doctor sign-off: closes the loop on a waiting patient. Only a clinician
    can do this — the AI never marks its own work as reviewed."""
    updated = await service.mark_reviewed(
        consultation_id, doctor_id=user.id, doctor_name=user.full_name
    )
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
    await audit_record(
        AuditAction.REVIEW_CONSULTATION,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="consultation", entity_id=consultation_id,
        patient_id=updated.patient_id,
    )
    consultation = await service.get_detail(consultation_id)
    assert_may_access(user, consultation.department)
    return ConsultationDetailOut.model_validate(consultation)
