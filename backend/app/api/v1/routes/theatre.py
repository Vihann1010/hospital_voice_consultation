"""Operation theatre endpoints: masters, bookings, theatre times, the slip.

Reading the theatre is everyday clinical work. Booking and cancelling a case is
the doctor's; recording the theatre times is shared with theatre nurses, who
are the ones standing at the door. The operation list carries price codes, so
editing it is master data management, like the consultant register.
"""
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.clock import local_today
from app.core.permissions import Permission
from app.models.enums import AuditAction, Department, PadStatus
from app.models.ipd import Admission
from app.models.pad import PadDocument
from app.models.patient import Patient
from app.models.theatre import Operation, Surgery, TheatreRoom
from app.pads.defaults import REGISTRY
from app.printing.layout import load_layout
from app.schemas.theatre_schemas import (
    OperationIn,
    SurgeryBookIn,
    SurgeryCancelIn,
    SurgeryRescheduleIn,
    SurgeryTimeIn,
    TheatreRoomIn,
)
from app.services.theatre_service import TheatreError, TheatreService
from app.theatre import rules
from app.theatre.slip_pdf import render_surgery_slip

router = APIRouter(prefix="/theatre", tags=["theatre"])

READ = require_permission(Permission.PATIENT_READ)
SCHEDULE = require_permission(Permission.THEATRE_SCHEDULE)
RECORD = require_permission(Permission.THEATRE_RECORD)
MASTERS = require_permission(Permission.MASTER_MANAGE)

THEATRE_NOTES = [key for key, spec in REGISTRY.items() if spec.scope == "surgery"]


def _fail(exc: TheatreError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _room(room: TheatreRoom) -> Dict[str, Any]:
    return {"id": room.id, "code": room.code, "name": room.name,
            "is_active": room.is_active, "notes": room.notes}


def _operation(item: Operation) -> Dict[str, Any]:
    return {"id": item.id, "code": item.code, "name": item.name,
            "department": item.department.value if item.department else None,
            "grade": item.grade, "default_minutes": item.default_minutes,
            "service_code": item.service_code, "is_active": item.is_active, "notes": item.notes}


async def _surgery(session, surgery: Surgery) -> Dict[str, Any]:
    patient = await session.get(Patient, surgery.patient_id)
    admission = await session.get(Admission, surgery.admission_id) if surgery.admission_id else None
    rows = (
        await session.execute(
            select(PadDocument.document_type, PadDocument.status).where(
                PadDocument.surgery_id == surgery.id,
                PadDocument.status != PadStatus.SUPERSEDED,
            )
        )
    ).all()
    states: Dict[str, str] = {}
    for document_type, document_status in rows:
        if document_status == PadStatus.SIGNED or document_type not in states:
            states[document_type] = document_status.value
    times = surgery.times()
    return {
        "id": surgery.id,
        "ot_number": surgery.ot_number,
        "status": surgery.status.value,
        "patient": {
            "id": patient.id, "name": patient.name, "uhid": patient.uhid,
            "age": patient.age, "gender": patient.gender.value,
        } if patient else None,
        "admission_id": surgery.admission_id,
        "visit_id": surgery.visit_id,
        "ip_number": admission.ip_number if admission else None,
        # A day case: no bed, and the bill goes to the visit.
        "day_case": surgery.admission_id is None,
        "allergies": (admission.allergies or []) if admission else [],
        "department": surgery.department.value,
        "operation_id": surgery.operation_id,
        "operation_name": surgery.operation_name,
        "laterality": surgery.laterality,
        "diagnosis": surgery.diagnosis,
        "surgeon_consultant_id": surgery.surgeon_consultant_id,
        "surgeon_name": surgery.surgeon_name,
        "assistants": surgery.assistants or [],
        "anaesthetist_name": surgery.anaesthetist_name,
        "anaesthesia_type": surgery.anaesthesia_type,
        "room_id": surgery.room_id,
        "room_name": surgery.room_name,
        "scheduled_at": surgery.scheduled_at,
        "expected_minutes": surgery.expected_minutes,
        "priority": surgery.priority,
        **times,
        "durations": rules.durations(times),
        "charge_reference": surgery.charge_reference,
        "cancel_reason": surgery.cancel_reason,
        "notes": surgery.notes,
        "booked_by_name": surgery.booked_by_name,
        "charge_reference": surgery.charge_reference,
        "documents": [
            {"document_type": key, "label": REGISTRY[key].label,
             "authority": REGISTRY[key].authority, "status": states.get(key, "missing")}
            for key in THEATRE_NOTES
        ],
        "created_at": surgery.created_at,
    }


# ------------------------------------------------------------------ options
@router.get("/options", dependencies=[Depends(READ)])
async def options() -> Dict[str, Any]:
    """The fixed choices a booking form offers, from the same lists the server checks."""
    return {
        "laterality": rules.LATERALITY,
        "anaesthesia_types": rules.ANAESTHESIA_TYPES,
        "priorities": rules.PRIORITIES,
        "grades": rules.GRADES,
        "milestones": [{"key": key, "label": rules.MILESTONE_LABEL[key]} for key in rules.MILESTONES],
    }


# ------------------------------------------------------------------ masters
@router.get("/rooms", dependencies=[Depends(READ)])
async def list_rooms(session: DbSession, include_inactive: bool = Query(default=False)) -> List[Dict[str, Any]]:
    return [_room(room) for room in await TheatreService(session).rooms(include_inactive=include_inactive)]


@router.post("/rooms", status_code=201, dependencies=[Depends(MASTERS)])
async def create_room(payload: TheatreRoomIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _room(await TheatreService(session).save_room(None, payload.model_dump()))
    except TheatreError as exc:
        raise _fail(exc) from exc


@router.put("/rooms/{room_id}", dependencies=[Depends(MASTERS)])
async def update_room(room_id: uuid.UUID, payload: TheatreRoomIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _room(await TheatreService(session).save_room(room_id, payload.model_dump()))
    except TheatreError as exc:
        raise _fail(exc) from exc


@router.get("/operations", dependencies=[Depends(READ)])
async def list_operations(
    session: DbSession,
    q: Optional[str] = Query(default=None, max_length=120),
    department: Optional[Department] = Query(default=None),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    found = await TheatreService(session).operations(
        q=q, department=department, include_inactive=include_inactive, limit=limit
    )
    return [_operation(item) for item in found]


@router.post("/operations", status_code=201, dependencies=[Depends(MASTERS)])
async def create_operation(payload: OperationIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _operation(await TheatreService(session).save_operation(None, payload.model_dump()))
    except TheatreError as exc:
        raise _fail(exc) from exc


@router.put("/operations/{operation_id}", dependencies=[Depends(MASTERS)])
async def update_operation(operation_id: uuid.UUID, payload: OperationIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _operation(await TheatreService(session).save_operation(operation_id, payload.model_dump()))
    except TheatreError as exc:
        raise _fail(exc) from exc


# -------------------------------------------------------------------- cases
@router.get("/surgeries", dependencies=[Depends(READ)])
async def list_surgeries(
    session: DbSession,
    on: Optional[date] = Query(default=None),
    admission_id: Optional[uuid.UUID] = Query(default=None),
    room_id: Optional[uuid.UUID] = Query(default=None),
) -> List[Dict[str, Any]]:
    """A day's theatre list, or every case on one admission."""
    day = on if (on or admission_id) else local_today()
    surgeries = await TheatreService(session).list(on=day, admission_id=admission_id, room_id=room_id)
    return [await _surgery(session, item) for item in surgeries]


@router.post("/surgeries", status_code=201, dependencies=[Depends(SCHEDULE)])
async def book_surgery(
    payload: SurgeryBookIn, session: DbSession, user: CurrentUser, request: Request
) -> Dict[str, Any]:
    try:
        surgery = await TheatreService(session).book(payload.model_dump(), user=user)
    except TheatreError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.SURGERY_BOOK,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="surgery", entity_id=surgery.id, patient_id=surgery.patient_id,
        ip_address=client_ip(request),
        detail={"ot_number": surgery.ot_number, "operation": surgery.operation_name,
                "side": surgery.laterality, "priority": surgery.priority,
                "overlap_allowed": payload.allow_overlap},
    )
    return await _surgery(session, surgery)


@router.get("/surgeries/{surgery_id}", dependencies=[Depends(READ)])
async def get_surgery(surgery_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    try:
        surgery = await TheatreService(session).get(surgery_id)
    except TheatreError as exc:
        raise _fail(exc) from exc
    return await _surgery(session, surgery)


@router.post("/surgeries/{surgery_id}/reschedule", dependencies=[Depends(SCHEDULE)])
async def reschedule_surgery(
    surgery_id: uuid.UUID, payload: SurgeryRescheduleIn, session: DbSession, user: CurrentUser
) -> Dict[str, Any]:
    try:
        surgery = await TheatreService(session).reschedule(
            surgery_id, payload.model_dump(exclude_unset=True), user=user
        )
    except TheatreError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return await _surgery(session, surgery)


@router.post("/surgeries/{surgery_id}/cancel", dependencies=[Depends(SCHEDULE)])
async def cancel_surgery(
    surgery_id: uuid.UUID, payload: SurgeryCancelIn, session: DbSession,
    user: CurrentUser, request: Request,
) -> Dict[str, Any]:
    try:
        surgery = await TheatreService(session).cancel(surgery_id, reason=payload.reason, user=user)
    except TheatreError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.SURGERY_CANCEL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="surgery", entity_id=surgery.id, patient_id=surgery.patient_id,
        ip_address=client_ip(request),
        detail={"ot_number": surgery.ot_number, "reason": payload.reason},
    )
    return await _surgery(session, surgery)


@router.post("/surgeries/{surgery_id}/times", dependencies=[Depends(RECORD)])
async def record_theatre_time(
    surgery_id: uuid.UUID, payload: SurgeryTimeIn, session: DbSession,
    user: CurrentUser, request: Request,
) -> Dict[str, Any]:
    try:
        result = await TheatreService(session).record_time(
            surgery_id, milestone=payload.milestone, at=payload.at, user=user
        )
    except TheatreError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    surgery = result["surgery"]
    await audit_record(
        AuditAction.SURGERY_TIME,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="surgery", entity_id=surgery.id, patient_id=surgery.patient_id,
        ip_address=client_ip(request),
        detail={"ot_number": surgery.ot_number, "milestone": payload.milestone,
                "at": getattr(surgery, payload.milestone).isoformat(),
                "status": surgery.status.value},
    )
    return {**await _surgery(session, surgery), "charge_note": result["charge_note"]}


@router.get("/surgeries/{surgery_id}/slip", dependencies=[Depends(READ)])
async def surgery_slip(surgery_id: uuid.UUID, session: DbSession) -> Response:
    """The printed slip that travels with the patient to theatre."""
    try:
        surgery = await TheatreService(session).get(surgery_id)
    except TheatreError as exc:
        raise _fail(exc) from exc
    patient = await session.get(Patient, surgery.patient_id)
    admission = await session.get(Admission, surgery.admission_id) if surgery.admission_id else None
    layout = await load_layout(session, "ot_slip")
    pdf = render_surgery_slip(surgery=surgery, patient=patient, admission=admission, layout=layout)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{surgery.ot_number}.pdf"'},
    )
