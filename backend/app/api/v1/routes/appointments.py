"""Appointments, the slot finder, and the day's queue board."""
import uuid
from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import (
    CurrentUser,
    get_appointment_service,
    get_reception_service,
    require_permission,
)
from app.core.audit import client_ip, record as audit_record
from app.core.clock import local_today, to_local
from app.core.permissions import Permission
from app.models.enums import AppointmentStatus, AuditAction, Department
from app.models.patient import Patient
from app.schemas.appointment_schemas import (
    AppointmentBookRequest,
    AppointmentCancelRequest,
    AppointmentCheckInRequest,
    AppointmentOut,
    AppointmentRescheduleRequest,
    AppointmentStatusRequest,
    BoardOut,
    NextSlotOut,
    SlotOut,
)
from app.schemas.emr_schemas import VisitOut
from app.services.appointment_service import AppointmentError, AppointmentService
from app.services.reception_service import ReceptionError, ReceptionService

router = APIRouter(prefix="/appointments", tags=["appointments"])

Service = Annotated[AppointmentService, Depends(get_appointment_service)]
Reception = Annotated[ReceptionService, Depends(get_reception_service)]

READ_BOARD = require_permission(Permission.APPOINTMENT_READ)
MANAGE = require_permission(Permission.APPOINTMENT_MANAGE)
# Checking a patient in creates a visit, so it needs the authority to open
# one — holding the diary is not the same as registering an attendance.
CHECK_IN = require_permission(Permission.APPOINTMENT_MANAGE, Permission.VISIT_CREATE)


@router.get("/slots", response_model=List[SlotOut], dependencies=[Depends(READ_BOARD)])
async def slots(
    service: Service,
    consultant_id: uuid.UUID = Query(...),
    on: date = Query(..., description="The day to show, in hospital local time"),
) -> List[SlotOut]:
    try:
        found = await service.available_slots(consultant_id=consultant_id, on=on)
    except AppointmentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return [SlotOut(**slot) for slot in found]


@router.get("/next-slot", response_model=NextSlotOut, dependencies=[Depends(READ_BOARD)])
async def next_slot(
    service: Service,
    consultant_id: uuid.UUID = Query(...),
    on: Optional[date] = Query(default=None),
    search_days: int = Query(default=14, ge=1, le=90),
) -> NextSlotOut:
    """The question reception is actually asked: when can they come in?"""
    try:
        found = await service.next_available(
            consultant_id=consultant_id, on=on, search_days=search_days
        )
    except AppointmentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return NextSlotOut(consultant_id=consultant_id, next_available=found)


@router.get("/board", response_model=BoardOut, dependencies=[Depends(READ_BOARD)])
async def board(
    service: Service,
    on: Optional[date] = Query(default=None),
    department: Optional[Department] = Query(default=None),
    consultant_id: Optional[uuid.UUID] = Query(default=None),
) -> BoardOut:
    """Bookings and walk-ins for one day, in one list."""
    return BoardOut(**await service.board(
        on=on, department=department, consultant_id=consultant_id
    ))


@router.get("", response_model=List[AppointmentOut], dependencies=[Depends(READ_BOARD)])
async def list_appointments(
    service: Service,
    on: Optional[date] = Query(default=None),
    consultant_id: Optional[uuid.UUID] = Query(default=None),
    department: Optional[Department] = Query(default=None),
    appointment_status: Optional[AppointmentStatus] = Query(default=None, alias="status"),
) -> List[AppointmentOut]:
    rows = await service.list_for_day(
        on=on, consultant_id=consultant_id, department=department,
        status=appointment_status,
    )
    # The board rows carry the patient's name; the appointment list is the
    # record itself, so it is re-read from the model rather than reshaped.
    found = [await service.get(row["id"]) for row in rows]
    return [AppointmentOut.model_validate(item) for item in found if item is not None]


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(MANAGE)])
async def book(
    payload: AppointmentBookRequest, service: Service, user: CurrentUser,
    request: Request,
) -> AppointmentOut:
    try:
        appointment = await service.book(
            **payload.model_dump(), booked_by_name=user.full_name
        )
        await service.session.commit()
    except AppointmentError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.APPOINTMENT_BOOK,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="appointment", entity_id=appointment.id,
        patient_id=appointment.patient_id, ip_address=client_ip(request),
        detail={"consultant": appointment.consultant_name,
                "start": appointment.scheduled_start.isoformat()},
    )
    return AppointmentOut.model_validate(appointment)


@router.get("/{appointment_id}", response_model=AppointmentOut,
            dependencies=[Depends(READ_BOARD)])
async def get_appointment(appointment_id: uuid.UUID, service: Service) -> AppointmentOut:
    appointment = await service.get(appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    return AppointmentOut.model_validate(appointment)


@router.post("/{appointment_id}/reschedule", response_model=AppointmentOut,
             dependencies=[Depends(MANAGE)])
async def reschedule(
    appointment_id: uuid.UUID, payload: AppointmentRescheduleRequest, service: Service
) -> AppointmentOut:
    try:
        appointment = await service.reschedule(
            appointment_id, scheduled_start=payload.scheduled_start
        )
        await service.session.commit()
    except AppointmentError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AppointmentOut.model_validate(appointment)


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut,
             dependencies=[Depends(MANAGE)])
async def cancel(
    appointment_id: uuid.UUID, payload: AppointmentCancelRequest, service: Service,
    user: CurrentUser, request: Request,
) -> AppointmentOut:
    try:
        appointment = await service.cancel(appointment_id, reason=payload.reason)
        await service.session.commit()
    except AppointmentError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.APPOINTMENT_CANCEL,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="appointment", entity_id=appointment.id,
        patient_id=appointment.patient_id, ip_address=client_ip(request),
        detail={"reason": payload.reason},
    )
    return AppointmentOut.model_validate(appointment)


@router.post("/{appointment_id}/status", response_model=AppointmentOut,
             dependencies=[Depends(MANAGE)])
async def set_status(
    appointment_id: uuid.UUID, payload: AppointmentStatusRequest, service: Service
) -> AppointmentOut:
    """Move a patient along the board: waiting, with the doctor, done."""
    try:
        appointment = await service.set_status(appointment_id, status=payload.status)
        await service.session.commit()
    except AppointmentError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AppointmentOut.model_validate(appointment)


@router.post("/{appointment_id}/check-in", response_model=VisitOut,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(CHECK_IN)])
async def check_in(
    appointment_id: uuid.UUID, payload: AppointmentCheckInRequest,
    service: Service, reception: Reception, user: CurrentUser,
) -> VisitOut:
    """The patient has arrived: turn the booking into a registered visit.

    Billing is deliberately not folded in here. A booking says who is coming
    and when; what they are charged depends on what is actually done, and the
    counter raises that invoice against the visit this returns. Doing both in
    one step would mean guessing the bill at booking time.
    """
    appointment = await service.get(appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")

    # A visit is dated the day it happens, so checking in a booking for next
    # Monday would register an attendance today against an appointment that
    # has not occurred — and take a token in today's queue for a patient who
    # is not in the building.
    booked_for = to_local(appointment.scheduled_start).date()
    if booked_for != local_today():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This appointment is for {booked_for:%d %b %Y}. Register the patient as a "
            "walk-in if they have come in early, or move the booking to today.",
        )

    try:
        # For a phone booking this is the moment the patient record is made.
        # It happens inside the same transaction as the visit, so a failure
        # halfway cannot leave a registered patient with no attendance and a
        # UHID nobody issued a token against.
        patient_id = appointment.patient_id
        if patient_id is None:
            if payload.patient_id is not None:
                linked = await service.session.get(Patient, payload.patient_id)
                if linked is None:
                    raise ReceptionError("That patient record no longer exists.")
                patient_id = linked.id
            elif payload.new_patient is not None:
                created = await reception.register_patient(
                    **payload.new_patient.model_dump()
                )
                patient_id = created.id
            else:
                raise ReceptionError(
                    f"{appointment.caller_name or 'This caller'} is not registered yet. "
                    "Register them, or link the record if they are already on the list."
                )
            await service.link_patient(appointment_id, patient_id=patient_id)
        elif payload.patient_id is not None or payload.new_patient is not None:
            raise ReceptionError("This appointment already has a patient record.")

        visit = await reception.open_visit(
            patient_id=patient_id,
            department=appointment.department,
            doctor_id=None,
            doctor_name=appointment.consultant_name,
            visit_type=appointment.visit_type,
            referred_by=appointment.referred_by,
            registered_by_name=user.full_name,
            notes=payload.notes,
        )
        await service.attach_visit(appointment_id, visit_id=visit.id)
        await service.session.commit()
    except (AppointmentError, ReceptionError) as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    out = VisitOut.model_validate(visit)
    # The board and the token slip both show a name, not a visit number.
    patient = await service.session.get(Patient, visit.patient_id)
    out.patient_name = patient.name if patient else ""
    return out
