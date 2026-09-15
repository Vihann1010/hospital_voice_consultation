"""Diet orders against an admission, and the kitchen's sheet for a day.

The rules — when an order may start, what is served at each meal — are in
`app/diet/rules.py`. This service loads the ward around them.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import day_bounds, local_datetime
from app.core.config import settings
from app.diet import rules
from app.models.admission_leave import AdmissionLeave
from app.models.diet import DietMode, DietOrder
from app.models.enums import AdmissionStatus
from app.models.ipd import Admission, BedOccupancy
from app.models.patient import Patient
from app.models.user import User

ACTIVE = (AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED)


class DietError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def meal_times() -> List[tuple]:
    try:
        return rules.parse_meal_times(settings.DIET_MEAL_TIMES)
    except ValueError as exc:
        raise DietError(f"DIET_MEAL_TIMES is not set correctly: {exc}", status_code=500) from exc


class DietService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----------------------------------------------------------------- modes
    async def modes(self, *, include_inactive: bool = False) -> List[DietMode]:
        statement = select(DietMode).order_by(DietMode.position, DietMode.name)
        if not include_inactive:
            statement = statement.where(DietMode.is_active.is_(True))
        return list((await self.session.execute(statement)).scalars())

    async def save_mode(self, mode_id: Optional[uuid.UUID], data: Dict[str, Any]) -> DietMode:
        code = (data.get("code") or "").strip().upper()
        name = (data.get("name") or "").strip()
        if not code or not name:
            raise DietError("A diet needs a code and a name.")
        mode = None
        if mode_id is not None:
            mode = await self.session.get(DietMode, mode_id)
            if mode is None:
                raise DietError("That diet no longer exists.", status_code=404)
        clashes = (await self.session.execute(
            select(DietMode).where(or_(func.upper(DietMode.code) == code,
                                       func.lower(DietMode.name) == name.lower()))
        )).scalars()
        if any(other.id != mode_id for other in clashes):
            raise DietError("Another diet already uses that code or name.", status_code=409)
        if mode is None:
            mode = DietMode()
            self.session.add(mode)
        mode.code = code
        mode.name = name
        mode.description = (data.get("description") or "").strip() or None
        mode.is_nil_by_mouth = bool(data.get("is_nil_by_mouth"))
        mode.position = int(data.get("position") or 0)
        mode.is_active = bool(data.get("is_active", True))
        await self.session.flush()
        return mode

    # ---------------------------------------------------------------- orders
    async def orders(self, admission_id: uuid.UUID) -> List[DietOrder]:
        return list((await self.session.execute(
            select(DietOrder).where(DietOrder.admission_id == admission_id)
            .order_by(DietOrder.starts_at.desc(), DietOrder.created_at.desc())
        )).scalars())

    async def _admission(self, admission_id: uuid.UUID) -> Admission:
        admission = (await self.session.execute(
            select(Admission).where(Admission.id == admission_id).with_for_update()
        )).scalar_one_or_none()
        if admission is None:
            raise DietError("Admission not found.", status_code=404)
        if admission.status not in ACTIVE:
            raise DietError("This patient is no longer admitted.")
        return admission

    async def _open_order(self, admission_id: uuid.UUID) -> Optional[DietOrder]:
        return (await self.session.execute(
            select(DietOrder).where(DietOrder.admission_id == admission_id, DietOrder.ends_at.is_(None))
            .with_for_update()
        )).scalar_one_or_none()

    async def place_order(
        self, admission_id: uuid.UUID, *, mode_id: uuid.UUID, starts_at: Optional[datetime],
        instructions: Optional[str], user: User,
    ) -> DietOrder:
        admission = await self._admission(admission_id)
        mode = await self.session.get(DietMode, mode_id)
        if mode is None or not mode.is_active:
            raise DietError("Choose a diet from the list.")
        now = _now()
        start = starts_at or now
        if start.tzinfo is None:
            raise DietError("Give the start time with its time zone.")
        problem = rules.check_start(start, now=now, admitted_at=admission.admitted_at)
        if problem:
            raise DietError(problem)
        note = (instructions or "").strip() or None
        if note and len(note) > rules.MAX_INSTRUCTIONS:
            raise DietError(f"Keep the instructions under {rules.MAX_INSTRUCTIONS} characters.")

        current = await self._open_order(admission_id)
        if current is not None:
            if current.starts_at >= start:
                raise DietError(
                    f"{current.mode_name} is already ordered from a later time. "
                    "Stop that order before ordering an earlier one."
                )
            current.ends_at = start
            current.ended_by_name = user.full_name
            current.end_reason = "Replaced by a new diet order"
            await self.session.flush()

        order = DietOrder(
            admission_id=admission_id, mode_id=mode.id, mode_name=mode.name,
            is_nil_by_mouth=mode.is_nil_by_mouth, instructions=note, starts_at=start,
            ordered_by_id=user.id, ordered_by_name=user.full_name,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def stop(self, admission_id: uuid.UUID, *, reason: str, user: User) -> DietOrder:
        await self._admission(admission_id)
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise DietError("Say why the diet order is stopped.")
        current = await self._open_order(admission_id)
        if current is None:
            raise DietError("There is no diet order to stop.")
        now = _now()
        # An order that has not begun yet is closed at its own start, so it
        # never takes effect.
        current.ends_at = max(now, current.starts_at)
        current.ended_by_name = user.full_name
        current.end_reason = reason
        await self.session.flush()
        return current

    # --------------------------------------------------------------- kitchen
    async def kitchen(self, on: date) -> Dict[str, Any]:
        meals = [(label, local_datetime(on, at)) for label, at in meal_times()]
        start, _ = day_bounds(on)
        _, end = day_bounds(on)
        found = (await self.session.execute(
            select(Admission, Patient).join(Patient, Patient.id == Admission.patient_id)
            .where(
                Admission.status != AdmissionStatus.CANCELLED,
                Admission.admitted_at < end,
                or_(Admission.discharged_at.is_(None), Admission.discharged_at > start),
            )
        )).all()
        ids = [admission.id for admission, _ in found]
        occupancies: Dict[uuid.UUID, List[Dict[str, Any]]] = {key: [] for key in ids}
        leaves: Dict[uuid.UUID, List[Dict[str, Any]]] = {key: [] for key in ids}
        orders: Dict[uuid.UUID, List[Dict[str, Any]]] = {key: [] for key in ids}
        if ids:
            for row in (await self.session.execute(
                select(BedOccupancy).where(BedOccupancy.admission_id.in_(ids))
            )).scalars():
                occupancies[row.admission_id].append({"ward": row.ward_name, "bed": row.bed_label,
                                                      "started_at": row.started_at, "ended_at": row.ended_at})
            for row in (await self.session.execute(
                select(AdmissionLeave).where(AdmissionLeave.admission_id.in_(ids))
            )).scalars():
                leaves[row.admission_id].append({"started_at": row.started_at, "returned_at": row.returned_at})
            for row in (await self.session.execute(
                select(DietOrder).where(DietOrder.admission_id.in_(ids)).order_by(DietOrder.starts_at)
            )).scalars():
                orders[row.admission_id].append({
                    "mode_name": row.mode_name, "is_nil_by_mouth": row.is_nil_by_mouth,
                    "instructions": row.instructions, "starts_at": row.starts_at, "ends_at": row.ends_at,
                })
        entries = [{
            "id": str(admission.id), "ip_number": admission.ip_number, "patient_name": patient.name,
            "age": patient.age, "gender": patient.gender.value, "allergies": admission.allergies or [],
            "admitted_at": admission.admitted_at, "discharged_at": admission.discharged_at,
            "occupancies": occupancies[admission.id], "leaves": leaves[admission.id],
            "orders": orders[admission.id],
        } for admission, patient in found]
        rows, counts = rules.build_sheet(entries, meals)
        return {
            "on": on.isoformat(),
            "meals": [{"label": label, "at": moment.isoformat()} for label, moment in meals],
            "rows": rows,
            "counts": counts,
        }
