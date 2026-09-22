"""The operation theatre: booking cases, recording theatre times, billing them.

The rules about time order, room clashes and case states are in
`app/theatre/rules.py`. What this service adds is the hospital around them:

* **An elective case is not wheeled in until a pre-procedure checklist is
  signed.** The checklist is where consent and fasting are confirmed, and a
  theatre that can start a case without it will. Either checklist counts: the
  surgical one, which marks the operation site, or the day-procedure one, which
  asks instead about sedation and who is taking the patient home — a gastroscopy
  has no site to mark, and a required box that cannot truthfully be ticked
  teaches a ward that the checks are paperwork. An emergency is marked as one
  and goes ahead; that is a decision someone makes on the booking, not a box
  skipped at the theatre door.
* **A room that is already booked is refused**, unless the person booking
  says they mean it — two lists sharing a room is sometimes deliberate.
* **A completed case on an admission is billed once**, from the operation
  list's price code, and a charge that cannot be posted never stops the
  patient being wheeled out; it is reported instead.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import day_bounds, local_today, to_local
from app.core.logging import get_logger
from app.models.consultant import Consultant
from app.models.emr import DocumentCounter, ServiceItem, Visit
from app.models.enums import (
    AdmissionStatus,
    ChargeCategory,
    Department,
    PadStatus,
    SurgeryStatus,
)
from app.models.ipd import Admission
from app.models.pad import PadDocument
from app.models.patient import Patient
from app.models.theatre import Operation, Surgery, TheatreRoom
from app.models.user import User
from app.theatre import rules

logger = get_logger(__name__)

# Either checklist admits a patient to theatre. The surgical one marks the
# operation site; the day-procedure one asks who is taking the patient home.
# Both confirm identity, consent and fasting, which is what the door is for.
PRE_OP_CHECKLIST = "ot_pre_op_checklist"
DAY_PROCEDURE_CHECKLIST = "ot_day_procedure_checklist"
DENTAL_CHECKLIST = "ot_dental_checklist"
PRE_PROCEDURE_CHECKLISTS = (PRE_OP_CHECKLIST, DAY_PROCEDURE_CHECKLIST, DENTAL_CHECKLIST)

# The notes a case is written up in, by department. Every case used to be
# offered every note — a scope was given an operation note and a pre-
# anaesthetic assessment, and would have given a filling the same. A
# department not listed here operates, and gets the surgical set.
SURGICAL_NOTES = ("ot_pre_op_checklist", "ot_pre_anaesthetic", "ot_operation_note",
                  "ot_post_op_orders")
DEPARTMENT_NOTES = {
    Department.GASTROENTEROLOGY: ("ot_day_procedure_checklist", "ot_endoscopy_report"),
    Department.DENTISTRY: ("ot_dental_checklist", "ot_dental_note"),
}


def notes_for(department: Department) -> tuple:
    return DEPARTMENT_NOTES.get(department, SURGICAL_NOTES)


class TheatreError(Exception):
    """A theatre request that cannot be honoured, with a reason to show."""

    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TheatreService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ================================================================ masters
    async def rooms(self, *, include_inactive: bool = False) -> List[TheatreRoom]:
        statement = select(TheatreRoom).order_by(TheatreRoom.code)
        if not include_inactive:
            statement = statement.where(TheatreRoom.is_active.is_(True))
        return list((await self.session.execute(statement)).scalars())

    async def save_room(self, room_id: Optional[uuid.UUID], data: Dict[str, Any]) -> TheatreRoom:
        if room_id is None:
            room = TheatreRoom()
            self.session.add(room)
        else:
            room = await self.session.get(TheatreRoom, room_id)
            if room is None:
                raise TheatreError("That theatre room no longer exists.", status_code=404)
        room.code = str(data["code"]).strip().upper()
        room.name = str(data["name"]).strip()
        room.is_active = bool(data.get("is_active", True))
        room.notes = data.get("notes")
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise TheatreError(f"A theatre room with code {room.code} already exists.", status_code=409) from exc
        return room

    async def operations(
        self,
        *,
        q: Optional[str] = None,
        department=None,
        include_inactive: bool = False,
        limit: int = 50,
    ) -> List[Operation]:
        statement = select(Operation)
        if not include_inactive:
            statement = statement.where(Operation.is_active.is_(True))
        if department is not None:
            statement = statement.where(
                or_(Operation.department.is_(None), Operation.department == department)
            )
        term = (q or "").strip()
        if term:
            like = f"%{term.replace('%', '').replace('_', '')}%"
            statement = statement.where(or_(Operation.name.ilike(like), Operation.code.ilike(like)))
        statement = statement.order_by(Operation.name).limit(limit)
        return list((await self.session.execute(statement)).scalars())

    async def save_operation(self, operation_id: Optional[uuid.UUID], data: Dict[str, Any]) -> Operation:
        if operation_id is None:
            operation = Operation()
            self.session.add(operation)
        else:
            operation = await self.session.get(Operation, operation_id)
            if operation is None:
                raise TheatreError("That operation no longer exists.", status_code=404)
        grade = data.get("grade")
        if grade and grade not in rules.GRADES:
            raise TheatreError(f"Grade must be one of: {', '.join(rules.GRADES)}.")
        operation.code = str(data["code"]).strip().upper()
        operation.name = str(data["name"]).strip()
        operation.department = data.get("department")
        operation.grade = grade or None
        operation.default_minutes = int(data.get("default_minutes") or 60)
        operation.service_code = (data.get("service_code") or "").strip().upper() or None
        operation.is_active = bool(data.get("is_active", True))
        operation.notes = data.get("notes")
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise TheatreError(f"An operation with code {operation.code} already exists.", status_code=409) from exc
        return operation

    # =============================================================== numbering
    async def _next_ot_number(self) -> str:
        """OT numbers are sequential per year, from the shared document counter."""
        period = f"{local_today().year}"
        lookup = (
            select(DocumentCounter)
            .where(DocumentCounter.scope == "ot", DocumentCounter.period == period)
            .with_for_update()
        )
        counter = (await self.session.execute(lookup)).scalar_one_or_none()
        if counter is None:
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope="ot", period=period, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = (await self.session.execute(lookup)).scalar_one()
        counter.last_value += 1
        await self.session.flush()
        return f"OT{local_today().year % 100:02d}-{counter.last_value:05d}"

    # ================================================================ cases
    async def get(self, surgery_id: uuid.UUID, *, lock: bool = False) -> Surgery:
        statement = select(Surgery).where(Surgery.id == surgery_id)
        if lock:
            statement = statement.with_for_update()
        surgery = (await self.session.execute(statement)).scalar_one_or_none()
        if surgery is None:
            raise TheatreError("That surgery no longer exists.", status_code=404)
        return surgery

    async def _check_room(
        self,
        *,
        reference: str,
        room_id: Optional[uuid.UUID],
        starts_at: datetime,
        minutes: int,
        allow_overlap: bool,
    ) -> None:
        if room_id is None:
            return
        others = list(
            (
                await self.session.execute(
                    select(Surgery).where(
                        Surgery.room_id == room_id,
                        Surgery.status.in_([SurgeryStatus.SCHEDULED, SurgeryStatus.IN_THEATRE]),
                        Surgery.scheduled_at >= starts_at - timedelta(hours=24),
                        Surgery.scheduled_at < starts_at + timedelta(minutes=minutes),
                    )
                )
            ).scalars()
        )
        bookings = [rules.Booking(str(item.id), item.scheduled_at, item.expected_minutes) for item in others]
        found = rules.clashes(rules.Booking(reference, starts_at, minutes), bookings)
        if found and not allow_overlap:
            by_id = {str(item.id): item for item in others}
            detail = "; ".join(
                f"{by_id[b.reference].ot_number} at {to_local(b.starts_at):%H:%M} for {b.minutes} min"
                for b in found
            )
            raise TheatreError(
                f"The room is already booked then — {detail}. Choose another time or room, "
                "or book it anyway.",
                status_code=409,
            )

    async def book(self, data: Dict[str, Any], *, user: User) -> Surgery:
        admission: Optional[Admission] = None
        if data.get("admission_id"):
            admission = await self.session.get(Admission, data["admission_id"])
            if admission is None:
                raise TheatreError("Admission not found.", status_code=404)
        visit: Optional[Visit] = None
        if data.get("visit_id"):
            visit = await self.session.get(Visit, data["visit_id"])
            if visit is None:
                raise TheatreError("Visit not found.", status_code=404)
        patient_id = (
            data.get("patient_id")
            or (admission.patient_id if admission else None)
            or (visit.patient_id if visit else None)
        )
        if patient_id is None:
            raise TheatreError("Choose the patient.")
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise TheatreError("Patient not found.", status_code=404)
        if visit is not None and visit.patient_id != patient.id:
            raise TheatreError("That visit belongs to another patient.")
        if admission is not None and visit is not None:
            raise TheatreError(
                "A case is billed to an admission or to a visit, not to both."
            )
        if admission is not None:
            if admission.patient_id != patient.id:
                raise TheatreError("That admission belongs to another patient.")
            if admission.status not in (AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED):
                raise TheatreError("That admission has already been discharged.", status_code=409)

        operation: Optional[Operation] = None
        if data.get("operation_id"):
            operation = await self.session.get(Operation, data["operation_id"])
            if operation is None or not operation.is_active:
                raise TheatreError("That operation is not on the active operation list.")
        name = (data.get("operation_name") or (operation.name if operation else "")).strip()
        if not name:
            raise TheatreError("Choose an operation from the list, or type what is being done.")

        laterality = data.get("laterality")
        if laterality not in rules.LATERALITY:
            raise TheatreError("Say which side: Left, Right, Bilateral, or Not applicable.")
        priority = (data.get("priority") or "elective").lower()
        if priority not in rules.PRIORITIES:
            raise TheatreError("Priority must be elective or emergency.")
        anaesthesia = data.get("anaesthesia_type") or None
        if anaesthesia and anaesthesia not in rules.ANAESTHESIA_TYPES:
            raise TheatreError(f"Anaesthesia must be one of: {', '.join(rules.ANAESTHESIA_TYPES)}.")

        consultant: Optional[Consultant] = None
        surgeon_name = (data.get("surgeon_name") or "").strip()
        if data.get("surgeon_consultant_id"):
            consultant = await self.session.get(Consultant, data["surgeon_consultant_id"])
            if consultant is None:
                raise TheatreError("That surgeon is not on the consultant register.", status_code=404)
            surgeon_name = consultant.full_name
        if not surgeon_name:
            raise TheatreError("Name the operating surgeon.")

        room: Optional[TheatreRoom] = None
        if data.get("room_id"):
            room = await self.session.get(TheatreRoom, data["room_id"])
            if room is None or not room.is_active:
                raise TheatreError("That theatre room is not in use.")

        scheduled_at: datetime = data["scheduled_at"]
        if scheduled_at.tzinfo is None:
            raise TheatreError("Give the time with its timezone.")
        minutes = int(data.get("expected_minutes") or (operation.default_minutes if operation else 60))
        if not 5 <= minutes <= 1440:
            raise TheatreError("Expected duration must be between 5 minutes and 24 hours.")

        department = (
            data.get("department")
            or (admission.department if admission else None)
            or (visit.department if visit else None)
            or (operation.department if operation else None)
            or (consultant.department if consultant else None)
        )
        if department is None:
            raise TheatreError("Say which department this surgery is under.")

        teeth: Optional[str] = None
        if department is Department.DENTISTRY:
            try:
                teeth = rules.parse_teeth(data.get("teeth"))
            except rules.TheatreRuleError as exc:
                raise TheatreError(str(exc)) from exc

        await self._check_room(
            reference="new", room_id=room.id if room else None, starts_at=scheduled_at,
            minutes=minutes, allow_overlap=bool(data.get("allow_overlap")),
        )

        surgery = Surgery(
            ot_number=await self._next_ot_number(),
            patient_id=patient.id,
            admission_id=admission.id if admission else None,
            visit_id=visit.id if visit else None,
            department=department,
            operation_id=operation.id if operation else None,
            operation_name=name[:255],
            laterality=laterality,
            teeth=teeth,
            diagnosis=(data.get("diagnosis") or (admission.provisional_diagnosis if admission else None)),
            surgeon_consultant_id=consultant.id if consultant else None,
            surgeon_name=surgeon_name,
            assistants=[str(item).strip() for item in data.get("assistants") or [] if str(item).strip()],
            anaesthetist_name=(data.get("anaesthetist_name") or "").strip() or None,
            anaesthesia_type=anaesthesia,
            room_id=room.id if room else None,
            room_name=room.name if room else None,
            scheduled_at=scheduled_at,
            expected_minutes=minutes,
            priority=priority,
            status=SurgeryStatus.SCHEDULED,
            notes=data.get("notes"),
            booked_by_name=user.full_name,
        )
        self.session.add(surgery)
        await self.session.commit()
        logger.info(
            "surgery_booked",
            extra={"ot_number": surgery.ot_number, "operation": surgery.operation_name,
                   "side": surgery.laterality, "by": user.full_name},
        )
        return surgery

    async def reschedule(self, surgery_id: uuid.UUID, data: Dict[str, Any], *, user: User) -> Surgery:
        surgery = await self.get(surgery_id, lock=True)
        if surgery.status != SurgeryStatus.SCHEDULED:
            raise TheatreError("Only a case that has not started can be rescheduled.", status_code=409)

        room = None
        if "room_id" in data:
            if data["room_id"]:
                room = await self.session.get(TheatreRoom, data["room_id"])
                if room is None or not room.is_active:
                    raise TheatreError("That theatre room is not in use.")
            surgery.room_id = room.id if room else None
            surgery.room_name = room.name if room else None
        if data.get("scheduled_at") is not None:
            if data["scheduled_at"].tzinfo is None:
                raise TheatreError("Give the time with its timezone.")
            surgery.scheduled_at = data["scheduled_at"]
        if data.get("expected_minutes"):
            surgery.expected_minutes = int(data["expected_minutes"])
        if data.get("priority"):
            if data["priority"] not in rules.PRIORITIES:
                raise TheatreError("Priority must be elective or emergency.")
            surgery.priority = data["priority"]

        await self._check_room(
            reference=str(surgery.id), room_id=surgery.room_id, starts_at=surgery.scheduled_at,
            minutes=surgery.expected_minutes, allow_overlap=bool(data.get("allow_overlap")),
        )
        await self.session.commit()
        return surgery

    async def cancel(self, surgery_id: uuid.UUID, *, reason: str, user: User) -> Surgery:
        surgery = await self.get(surgery_id, lock=True)
        try:
            target = rules.next_status(surgery.status.value, "cancel")
        except rules.TheatreRuleError as exc:
            raise TheatreError(str(exc), status_code=409) from exc
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise TheatreError("Say why the case is being cancelled.")
        surgery.status = SurgeryStatus(target)
        surgery.cancel_reason = reason
        await self.session.commit()
        return surgery

    async def record_time(
        self,
        surgery_id: uuid.UUID,
        *,
        milestone: str,
        at: Optional[datetime],
        user: User,
    ) -> Dict[str, Any]:
        """Record one theatre time. Returns the surgery and any billing note."""
        surgery = await self.get(surgery_id, lock=True)
        now = _now()
        moment = at or now
        if moment.tzinfo is None:
            raise TheatreError("Give the time with its timezone.")
        current = surgery.status.value

        if milestone == "wheel_in_at" and current == "in_theatre":
            target = current  # correcting the wheel-in time
        elif milestone == "wheel_in_at":
            try:
                target = rules.next_status(current, "wheel_in")
            except rules.TheatreRuleError as exc:
                raise TheatreError(str(exc), status_code=409) from exc
            if surgery.priority != "emergency":
                signed = (
                    await self.session.execute(
                        select(PadDocument.id).where(
                            PadDocument.surgery_id == surgery.id,
                            PadDocument.document_type.in_(PRE_PROCEDURE_CHECKLISTS),
                            PadDocument.status == PadStatus.SIGNED,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if signed is None:
                    raise TheatreError(
                        "Sign the pre-procedure checklist before wheeling the patient in. If "
                        "this is an emergency, mark the case as an emergency first.",
                        status_code=409,
                    )
        elif milestone == "wheel_out_at":
            try:
                target = rules.next_status(current, "wheel_out")
            except rules.TheatreRuleError as exc:
                raise TheatreError(str(exc), status_code=409) from exc
        else:
            if current != "in_theatre":
                raise TheatreError(
                    f"{rules.MILESTONE_LABEL.get(milestone, milestone)} can only be recorded while "
                    "the patient is in theatre.",
                    status_code=409,
                )
            target = current

        try:
            times = rules.check_milestone(surgery.times(), milestone, moment, now=now)
        except rules.TheatreRuleError as exc:
            raise TheatreError(str(exc)) from exc

        setattr(surgery, milestone, times[milestone])
        surgery.status = SurgeryStatus(target)

        charge_note = None
        if target == "completed" and current != "completed":
            charge_note = await self._charge(surgery, user)

        await self.session.commit()
        return {"surgery": surgery, "charge_note": charge_note}

    async def _charge(self, surgery: Surgery, user: User) -> Optional[str]:
        """Bill a completed case once: to its admission, or to its visit.

        A day case has no admission and used to end here with "bill it at the
        counter", which in a clinic where every case is a day case means every
        procedure depends on somebody remembering. The visit is what the
        counter bills against, so the charge goes there — raised, not paid, so
        the patient still settles it at the counter like any other bill.
        """
        if surgery.charge_reference:
            return None
        if surgery.admission_id is None and surgery.visit_id is None:
            return (
                "This case is not linked to an admission or a visit, so no charge was "
                "raised. Bill it at the counter."
            )
        operation = await self.session.get(Operation, surgery.operation_id) if surgery.operation_id else None
        if operation is None or not operation.service_code:
            return (
                "This operation has no price-list code, so no theatre charge was posted. Add it "
                "to the bill by hand, or give the operation a code on the operation list."
            )

        if surgery.admission_id is None:
            return await self._charge_visit(surgery, operation, user)

        from app.services.ipd_service import IPDError, IPDService

        try:
            async with self.session.begin_nested():
                await IPDService(self.session).post_charge(
                    admission_id=surgery.admission_id,
                    category=ChargeCategory.PROCEDURE,
                    description=f"{surgery.operation_name} ({surgery.laterality}) — {surgery.ot_number}",
                    service_code=operation.service_code,
                    source_reference=surgery.ot_number,
                    posted_by_name=user.full_name,
                )
        except IPDError as exc:
            return f"The theatre charge was not posted: {exc}"
        surgery.charge_reference = surgery.ot_number
        return None

    async def _charge_visit(
        self, surgery: Surgery, operation: Operation, user: User
    ) -> Optional[str]:
        """Raise the day-case bill on the patient's visit.

        Issued, not paid: the counter takes the money, applies any discount and
        gives the receipt, exactly as for a consultation. Raising it here only
        means the procedure cannot be forgotten between the suite and the desk.
        """
        from app.services.reception_service import ReceptionError, ReceptionService

        description = f"{surgery.operation_name} — {surgery.ot_number}"
        quantity = 1
        teeth = rules.tooth_count(surgery.teeth)
        if teeth:
            description = f"{surgery.operation_name} — teeth {surgery.teeth} — {surgery.ot_number}"
            service = (
                await self.session.execute(
                    select(ServiceItem).where(ServiceItem.code == operation.service_code)
                )
            ).scalar_one_or_none()
            if service is not None and rules.PER_TOOTH_MARKER in service.name.lower():
                quantity = teeth
        try:
            async with self.session.begin_nested():
                invoice = await ReceptionService(self.session).create_invoice(
                    visit_id=surgery.visit_id,
                    patient_id=surgery.patient_id,
                    items=[{"code": operation.service_code, "description": description,
                            "quantity": quantity}],
                    consultant_id=surgery.surgeon_consultant_id,
                    doctor_name=surgery.surgeon_name,
                    created_by_name=user.full_name,
                    issue=True,
                )
        except ReceptionError as exc:
            return f"The procedure bill was not raised: {exc}. Bill it at the counter."
        surgery.charge_reference = invoice.invoice_number
        return (
            f"Bill {invoice.invoice_number} raised for this procedure. "
            "The patient pays it at the counter."
        )

    # ============================================================== reading
    async def list(
        self,
        *,
        on: Optional[date] = None,
        admission_id: Optional[uuid.UUID] = None,
        room_id: Optional[uuid.UUID] = None,
    ) -> List[Surgery]:
        statement = select(Surgery)
        if admission_id is not None:
            statement = statement.where(Surgery.admission_id == admission_id)
        if on is not None:
            start, end = day_bounds(on)
            # A case still in theatre from yesterday's list is still on today's board.
            statement = statement.where(
                or_(
                    and_(Surgery.scheduled_at >= start, Surgery.scheduled_at < end),
                    Surgery.status == SurgeryStatus.IN_THEATRE,
                )
            )
        if room_id is not None:
            statement = statement.where(Surgery.room_id == room_id)
        statement = statement.order_by(Surgery.scheduled_at)
        return list((await self.session.execute(statement)).scalars())
