"""Booking, the slot arithmetic, and the day's queue board.

Two decisions shape everything here.

**Slots are derived.** A consultant's day is their OPD window cut into their
own appointment length, minus whatever is already booked. Nothing stores the
empty ones. That way a consultant who changes their slot length from fifteen
minutes to twenty does not need a regeneration job, and there is no table
that can quietly disagree with the bookings themselves.

**The overlap check is serialised on the consultant.** Two receptionists
offering the same free slot to two patients at the same moment is not a
hypothetical — it is the normal failure of a booking screen. Checking for a
clash and then inserting is a read-then-write race, so the consultant's row
is locked for the duration, which makes the pair atomic. A partial unique
index backs it up at the database level for the exact-start case.
"""
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_datetime, local_now, local_today, to_local
from app.core.logging import get_logger
from app.models.appointment import Appointment
from app.models.consultant import Consultant
from app.models.emr import Visit
from app.models.enums import AppointmentStatus, Department, VisitStatus, VisitType
from app.models.patient import Patient

logger = get_logger(__name__)

# Statuses that still occupy the slot. A cancelled booking frees its time
# immediately — the whole point of cancelling it.
LIVE_STATUSES = (
    AppointmentStatus.PENDING,
    AppointmentStatus.WAITING,
    AppointmentStatus.ENGAGED,
    AppointmentStatus.DONE,
)

# What may follow what. Reception moves a patient forward through the board;
# nothing moves backwards, because a board that can be walked back is a board
# nobody trusts. Cancelling is handled separately and is refused once the
# patient has been seen.
_TRANSITIONS: Dict[AppointmentStatus, set] = {
    AppointmentStatus.PENDING: {AppointmentStatus.WAITING, AppointmentStatus.CANCELLED},
    AppointmentStatus.WAITING: {AppointmentStatus.ENGAGED, AppointmentStatus.CANCELLED},
    AppointmentStatus.ENGAGED: {AppointmentStatus.DONE},
    AppointmentStatus.DONE: set(),
    AppointmentStatus.CANCELLED: set(),
}


class AppointmentError(Exception):
    pass


def _weekdays(spec: str) -> set:
    """Parse "1,2,3" into ISO weekday numbers, ignoring anything malformed."""
    days = set()
    for part in spec.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= 7:
            days.add(int(part))
    return days


class AppointmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------- slots
    async def _consultant(self, consultant_id: uuid.UUID, *, lock: bool = False) -> Consultant:
        stmt = select(Consultant).where(Consultant.id == consultant_id)
        if lock:
            stmt = stmt.with_for_update()
        consultant = await self.session.scalar(stmt)
        if consultant is None:
            raise AppointmentError("Consultant not found.")
        return consultant

    async def _booked(self, consultant_id: uuid.UUID, on: date) -> List[Appointment]:
        """Every live booking for that consultant on that local day."""
        start = local_datetime(on, time.min)
        end = start + timedelta(days=1)
        result = await self.session.execute(
            select(Appointment)
            .where(
                Appointment.consultant_id == consultant_id,
                Appointment.scheduled_start >= start,
                Appointment.scheduled_start < end,
                Appointment.status.in_(LIVE_STATUSES),
            )
            .order_by(Appointment.scheduled_start)
        )
        return list(result.scalars())

    async def available_slots(
        self, *, consultant_id: uuid.UUID, on: date
    ) -> List[Dict[str, Any]]:
        """Every startable slot for a consultant on a day, free ones marked.

        Booked slots are returned too rather than filtered out, so the screen
        can show a full day at a glance instead of an unexplained gap.
        """
        consultant = await self._consultant(consultant_id)
        if not consultant.is_active:
            raise AppointmentError(f"{consultant.full_name} is no longer taking appointments.")
        if on.isoweekday() not in _weekdays(consultant.opd_days):
            return []

        length = max(consultant.appointment_minutes, 5)
        taken = await self._booked(consultant_id, on)
        now = local_now()

        slots: List[Dict[str, Any]] = []
        cursor = local_datetime(on, consultant.opd_start_time)
        closing = local_datetime(on, consultant.opd_end_time)
        while cursor + timedelta(minutes=length) <= closing:
            finish = cursor + timedelta(minutes=length)
            clash = next(
                (
                    booking
                    for booking in taken
                    if to_local(booking.scheduled_start) < finish
                    and to_local(booking.scheduled_start)
                    + timedelta(minutes=booking.duration_minutes)
                    > cursor
                ),
                None,
            )
            slots.append({
                "start": cursor,
                "end": finish,
                # A slot that has already passed is not bookable, but it is
                # still shown: the receptionist needs to see that the morning
                # is gone, not an empty list.
                "available": clash is None and cursor > now,
                "past": cursor <= now,
                "appointment_id": clash.id if clash else None,
            })
            cursor = finish
        return slots

    async def next_available(
        self, *, consultant_id: uuid.UUID, on: Optional[date] = None, search_days: int = 14
    ) -> Optional[datetime]:
        """The soonest free slot, looking forward across days.

        Reception is nearly always asked "when can they come" rather than
        "is Thursday at four free", so the answer to that question is one
        endpoint rather than something the screen assembles from fourteen
        separate day queries.
        """
        day = on or local_today()
        for offset in range(max(search_days, 1)):
            for slot in await self.available_slots(
                consultant_id=consultant_id, on=day + timedelta(days=offset)
            ):
                if slot["available"]:
                    return slot["start"]
        return None

    # ------------------------------------------------------------ booking
    async def book(
        self,
        *,
        patient_id: Optional[uuid.UUID] = None,
        caller: Optional[Dict[str, Any]] = None,
        consultant_id: uuid.UUID,
        scheduled_start: datetime,
        visit_type: VisitType = VisitType.NEW,
        reason: Optional[str] = None,
        referred_by: Optional[str] = None,
        booked_by_name: str = "",
    ) -> Appointment:
        """Book for a registered patient, or for somebody who just rang.

        The caller path exists because the alternative is worse: demanding a
        UHID to answer the telephone means registering strangers who may
        never arrive, and registering the same person again the next time
        they ring because nobody could find the record they made last month.
        """
        patient: Optional[Patient] = None
        if patient_id is not None:
            patient = await self.session.get(Patient, patient_id)
            if patient is None:
                raise AppointmentError("Patient not found.")
        elif not caller or not caller.get("name") or not caller.get("phone_number"):
            raise AppointmentError(
                "Give an existing patient, or a name and phone number to book them under."
            )

        # Locked for the rest of the transaction: the clash check below and
        # the insert that follows it have to be one indivisible step.
        consultant = await self._consultant(consultant_id, lock=True)
        if not consultant.is_active:
            raise AppointmentError(f"{consultant.full_name} is no longer taking appointments.")

        start = to_local(scheduled_start)
        if start <= local_now():
            raise AppointmentError("Appointments cannot be booked in the past.")
        if start.isoweekday() not in _weekdays(consultant.opd_days):
            raise AppointmentError(
                f"{consultant.full_name} does not sit in the OPD on a {start:%A}."
            )

        length = max(consultant.appointment_minutes, 5)
        finish = start + timedelta(minutes=length)
        if start.time() < consultant.opd_start_time or finish.time() > consultant.opd_end_time:
            raise AppointmentError(
                f"Outside {consultant.full_name}'s OPD hours "
                f"({consultant.opd_start_time:%H:%M}-{consultant.opd_end_time:%H:%M})."
            )

        for existing in await self._booked(consultant_id, start.date()):
            other_start = to_local(existing.scheduled_start)
            other_end = other_start + timedelta(minutes=existing.duration_minutes)
            if other_start < finish and other_end > start:
                raise AppointmentError(
                    f"{consultant.full_name} is already booked at {other_start:%H:%M}."
                )

        appointment = Appointment(
            patient_id=patient_id,
            caller_name=None if patient else (caller or {}).get("name"),
            caller_phone=None if patient else (caller or {}).get("phone_number"),
            caller_age=None if patient else (caller or {}).get("age"),
            caller_gender=None if patient else (caller or {}).get("gender"),
            consultant_id=consultant_id,
            consultant_name=consultant.full_name,
            department=consultant.department,
            scheduled_start=start,
            duration_minutes=length,
            status=AppointmentStatus.PENDING,
            visit_type=visit_type,
            reason=reason,
            referred_by=referred_by,
            booked_by_name=booked_by_name,
        )
        self.session.add(appointment)
        await self.session.flush()
        logger.info(
            "appointment_booked",
            extra={"uhid": patient.uhid if patient else "unregistered",
                   "consultant": consultant.full_name,
                   "start": start.isoformat()},
        )
        return appointment

    async def reschedule(
        self, appointment_id: uuid.UUID, *, scheduled_start: datetime
    ) -> Appointment:
        appointment = await self.get(appointment_id)
        if appointment is None:
            raise AppointmentError("Appointment not found.")
        if appointment.status is not AppointmentStatus.PENDING:
            raise AppointmentError(
                "Only a booking the patient has not arrived for can be moved."
            )
        # Cancel first, then rebook, so the old slot is genuinely released
        # before the new one is checked — otherwise a booking cannot be moved
        # half an hour later, because it clashes with itself.
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = local_now()
        appointment.cancellation_reason = "Rescheduled"
        await self.session.flush()
        return await self.book(
            patient_id=appointment.patient_id,
            caller={
                "name": appointment.caller_name,
                "phone_number": appointment.caller_phone,
                "age": appointment.caller_age,
                "gender": appointment.caller_gender,
            },
            consultant_id=appointment.consultant_id,
            scheduled_start=scheduled_start,
            visit_type=appointment.visit_type,
            reason=appointment.reason,
            referred_by=appointment.referred_by,
            booked_by_name=appointment.booked_by_name,
        )

    async def cancel(self, appointment_id: uuid.UUID, *, reason: str) -> Appointment:
        appointment = await self.get(appointment_id)
        if appointment is None:
            raise AppointmentError("Appointment not found.")
        if appointment.status in (AppointmentStatus.ENGAGED, AppointmentStatus.DONE):
            raise AppointmentError(
                "The patient has already been seen; this appointment cannot be cancelled."
            )
        if appointment.status is AppointmentStatus.CANCELLED:
            raise AppointmentError("Already cancelled.")
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = local_now()
        appointment.cancellation_reason = reason
        await self.session.flush()
        return appointment

    async def set_status(
        self, appointment_id: uuid.UUID, *, status: AppointmentStatus
    ) -> Appointment:
        appointment = await self.get(appointment_id)
        if appointment is None:
            raise AppointmentError("Appointment not found.")
        if status is appointment.status:
            return appointment
        if status not in _TRANSITIONS[appointment.status]:
            raise AppointmentError(
                f"An appointment cannot go from {appointment.status.value} to {status.value}."
            )
        if status is AppointmentStatus.WAITING and appointment.visit_id is None:
            raise AppointmentError(
                "Check the patient in — a booking becomes a visit before it joins the queue."
            )
        appointment.status = status
        # Carry the move onto the visit as well. The board and the counter's
        # "today" list read from different tables, and a patient shown as
        # finished on one and still waiting on the other is how the wrong
        # person gets called in.
        if appointment.visit_id is not None:
            visit = await self.session.get(Visit, appointment.visit_id)
            if visit is not None:
                mirrored = _to_visit_status(status)
                if mirrored is not None:
                    visit.status = mirrored
        await self.session.flush()
        return appointment

    async def attach_visit(
        self, appointment_id: uuid.UUID, *, visit_id: uuid.UUID
    ) -> Appointment:
        """Record that this booking has become a registered visit."""
        appointment = await self.get(appointment_id)
        if appointment is None:
            raise AppointmentError("Appointment not found.")
        if appointment.visit_id is not None:
            raise AppointmentError("This appointment has already been checked in.")
        if appointment.status is AppointmentStatus.CANCELLED:
            raise AppointmentError("This appointment was cancelled.")
        appointment.visit_id = visit_id
        appointment.status = AppointmentStatus.WAITING
        await self.session.flush()
        return appointment

    async def link_patient(
        self, appointment_id: uuid.UUID, *, patient_id: uuid.UUID
    ) -> Appointment:
        """Attach the patient record created (or found) at check-in.

        The caller's details are kept rather than cleared. They are what the
        clerk typed off a phone call, and if the wrong record was linked, the
        original words are the only way to tell.
        """
        appointment = await self.get(appointment_id)
        if appointment is None:
            raise AppointmentError("Appointment not found.")
        if appointment.patient_id is not None and appointment.patient_id != patient_id:
            raise AppointmentError(
                "This appointment is already against a different patient."
            )
        appointment.patient_id = patient_id
        await self.session.flush()
        return appointment

    # ------------------------------------------------------------ reading
    async def get(self, appointment_id: uuid.UUID) -> Optional[Appointment]:
        return await self.session.get(Appointment, appointment_id)

    async def list_for_day(
        self,
        *,
        on: Optional[date] = None,
        consultant_id: Optional[uuid.UUID] = None,
        department: Optional[Department] = None,
        status: Optional[AppointmentStatus] = None,
    ) -> List[Dict[str, Any]]:
        day = on or local_today()
        start = local_datetime(day, time.min)
        end = start + timedelta(days=1)

        conditions = [
            Appointment.scheduled_start >= start,
            Appointment.scheduled_start < end,
        ]
        if consultant_id is not None:
            conditions.append(Appointment.consultant_id == consultant_id)
        if department is not None:
            conditions.append(Appointment.department == department)
        if status is not None:
            conditions.append(Appointment.status == status)

        result = await self.session.execute(
            # Both joins are outer. A phone booking has no patient row yet,
            # and a booking nobody has checked in has no visit — an inner
            # join on either would silently drop exactly the rows the board
            # exists to show.
            select(Appointment, Patient, Visit)
            .outerjoin(Patient, Patient.id == Appointment.patient_id)
            .outerjoin(Visit, Visit.id == Appointment.visit_id)
            .where(and_(*conditions))
            .order_by(Appointment.scheduled_start)
        )
        return [
            _row(appointment, patient, visit)
            for appointment, patient, visit in result.all()
        ]

    async def board(
        self,
        *,
        on: Optional[date] = None,
        department: Optional[Department] = None,
        consultant_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """The day's queue, bookings and walk-ins together.

        Walk-ins are most of this OPD's morning, and a board that showed only
        booked patients would show a waiting room that does not exist. They
        appear as rows with no slot time, after the bookings.
        """
        day = on or local_today()
        booked = await self.list_for_day(
            on=day, department=department, consultant_id=consultant_id
        )
        claimed = {row["visit_id"] for row in booked if row["visit_id"]}

        conditions = [Visit.visit_date == day]
        if department is not None:
            conditions.append(Visit.department == department)
        result = await self.session.execute(
            select(Visit, Patient)
            .join(Patient, Patient.id == Visit.patient_id)
            .where(and_(*conditions))
            .order_by(Visit.token_number)
        )
        walk_ins = []
        for visit, patient in result.all():
            if visit.id in claimed:
                continue
            walk_ins.append({
                "id": None,
                "kind": "walk_in",
                "visit_id": visit.id,
                "visit_number": visit.visit_number,
                "token_number": visit.token_number,
                "patient_id": patient.id,
                "patient_name": patient.name,
                "uhid": patient.uhid,
                "registered": True,
                "phone_number": patient.phone_number,
                "consultant_name": visit.doctor_name,
                "department": visit.department.value,
                "scheduled_start": None,
                "duration_minutes": None,
                "visit_type": visit.visit_type.value,
                "reason": None,
                "status": _from_visit_status(visit.status).value,
            })

        rows = booked + walk_ins
        counts = {status.value: 0 for status in AppointmentStatus}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {"date": day, "counts": counts, "rows": rows}


def _to_visit_status(status: AppointmentStatus) -> Optional[VisitStatus]:
    """The reverse mapping, for the states a board move actually changes.

    Only three of the five say anything about the visit. "Pending" happens
    before a visit exists, and cancelling an appointment does not cancel an
    attendance that has already been registered and possibly billed — that is
    a decision for the counter, not a side effect of tidying the board.
    """
    return {
        AppointmentStatus.WAITING: VisitStatus.REGISTERED,
        AppointmentStatus.ENGAGED: VisitStatus.IN_CONSULTATION,
        AppointmentStatus.DONE: VisitStatus.COMPLETED,
    }.get(status)


def _from_visit_status(status: VisitStatus) -> AppointmentStatus:
    """Show a walk-in on the same board as a booking.

    A visit and an appointment track the same patient through the same
    morning under two different vocabularies, so one is mapped onto the other
    for display rather than the board learning both.
    """
    return {
        VisitStatus.REGISTERED: AppointmentStatus.WAITING,
        VisitStatus.IN_CONSULTATION: AppointmentStatus.ENGAGED,
        VisitStatus.COMPLETED: AppointmentStatus.DONE,
        VisitStatus.CANCELLED: AppointmentStatus.CANCELLED,
    }[status]


def _row(
    appointment: Appointment,
    patient: Optional[Patient],
    visit: Optional[Visit] = None,
) -> Dict[str, Any]:
    return {
        "id": appointment.id,
        "kind": "appointment",
        "visit_id": appointment.visit_id,
        # Once checked in, a booking has a visit like any walk-in — and
        # reception calls patients by token, not by appointment time.
        "visit_number": visit.visit_number if visit else None,
        "token_number": visit.token_number if visit else None,
        "patient_id": patient.id if patient else None,
        "patient_name": patient.name if patient else (appointment.caller_name or ""),
        # An empty UHID is the honest answer and the screen reads it as
        # "not registered yet" — inventing a placeholder here would put a
        # number on the board that matches nothing in the register.
        "uhid": patient.uhid if patient else "",
        "registered": patient is not None,
        "phone_number": patient.phone_number if patient else appointment.caller_phone,
        "consultant_name": appointment.consultant_name,
        "department": appointment.department.value,
        "scheduled_start": to_local(appointment.scheduled_start),
        "duration_minutes": appointment.duration_minutes,
        "visit_type": appointment.visit_type.value,
        "reason": appointment.reason,
        "status": appointment.status.value,
    }
