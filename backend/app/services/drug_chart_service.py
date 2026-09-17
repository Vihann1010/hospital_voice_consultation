"""The inpatient drug chart: prescribing, scheduling, signing and stopping.

What a ward runs its medicines from. The doctor prescribes; the schedule of
doses is laid out in hospital time; the nurse signs each dose as given, or not
given with a reason; the doctor stops it. The timing rules are in
`app/ipd/drug_chart.py`.

Prescribing on the ward runs the same deterministic safety checks as an OPD
prescription — allergies, duplicates, interactions — against the allergies
recorded on the admission and every medicine already running. A serious alert
must be acknowledged before the order is accepted, exactly as it must be in
OPD. A ward order is not a lesser prescription.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import day_bounds, to_local
from app.core.logging import get_logger
from app.ipd import drug_chart as rules
from app.models.enums import AdmissionStatus, MedicationRouteIPD, MedicationStatus
from app.models.ipd import Admission, MedicationAdministration, MedicationOrder
from app.models.user import User
from app.ai.pipeline.medication_rules import normalize_name
from app.prescriptions import formulary, safety

logger = get_logger(__name__)

ACTIVE_ADMISSION = (AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED)


class DrugChartError(Exception):
    """A drug chart request that cannot be honoured, with a reason to show."""

    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None,
                 alerts: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        self.alerts = alerts or []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clock(moment: datetime) -> str:
    return to_local(moment).strftime("%H:%M")


def _formulary_code(name: str) -> Optional[str]:
    """The formulary entry this name is, exactly — never a fuzzy guess.

    `formulary.match_by_name` falls back to a search hit, which would call
    "Pantocid DSR" the formulary's Pantoprazole and hide that the order is for
    something the hospital does not stock.
    """
    cleaned = normalize_name(name)
    if not cleaned:
        return None
    for item in formulary.FORMULARY:
        if normalize_name(item.name) == cleaned:
            return item.code
    for item in formulary.FORMULARY:
        if len(item.ingredients) == 1 and normalize_name(item.ingredients[0]) == cleaned:
            return item.code
    return None


class DrugChartService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------ helpers
    async def _admission(self, admission_id: uuid.UUID, *, lock: bool = False) -> Admission:
        statement = select(Admission).where(Admission.id == admission_id)
        if lock:
            statement = statement.with_for_update()
        admission = (await self.session.execute(statement)).scalar_one_or_none()
        if admission is None:
            raise DrugChartError("Admission not found.", status_code=404)
        return admission

    async def _order(self, order_id: uuid.UUID, *, lock: bool = False) -> MedicationOrder:
        statement = select(MedicationOrder).where(MedicationOrder.id == order_id)
        if lock:
            statement = statement.with_for_update()
        order = (await self.session.execute(statement)).scalar_one_or_none()
        if order is None:
            raise DrugChartError("That medicine order no longer exists.", status_code=404)
        return order

    async def _reload(self, order_id: uuid.UUID) -> MedicationOrder:
        return (
            await self.session.execute(
                select(MedicationOrder)
                .options(selectinload(MedicationOrder.administrations))
                .where(MedicationOrder.id == order_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()

    # ------------------------------------------------------------- safety
    async def check(self, admission_id: uuid.UUID, *, drug_name: str) -> Dict[str, Any]:
        """Alerts a new order would raise against this admission.

        Only alerts that involve the new medicine are returned. Two medicines
        already running that interact were accepted when the second was
        prescribed; repeating that on every new order teaches people to click
        past alerts.
        """
        admission = await self._admission(admission_id)
        name = (drug_name or "").strip()
        allergies = [item for item in (admission.allergies or []) if str(item).strip()]
        if not name:
            return {"alerts": [], "blocking": 0, "allergies": allergies}

        running = (
            await self.session.execute(
                select(MedicationOrder.drug_name).where(
                    MedicationOrder.admission_id == admission_id,
                    MedicationOrder.status == MedicationStatus.ACTIVE,
                )
            )
        ).scalars().all()
        # The OPD checker also audits each row for a formulary code and a
        # frequency. Passed bare names, it warned "not in the formulary" and
        # "no frequency set" about every medicine, running ones included — two
        # cautions per drug on every order, which is how people learn to stop
        # reading alerts. Codes are resolved exactly here, and the frequency is
        # validated by the order itself.
        entries = [
            {"name": drug, "formulary_code": _formulary_code(drug), "frequency_code": "ward"}
            for drug in [*running, name]
        ]
        involved = name.lower()
        alerts = [
            alert for alert in safety.run_all(entries, allergies=allergies)
            if any(str(item).strip().lower() == involved for item in alert.medicines)
        ]
        return {
            "alerts": [alert.to_dict() for alert in alerts],
            "blocking": len(safety.blocking_alerts(alerts)),
            "allergies": allergies,
        }

    # --------------------------------------------------------- prescribing
    async def order(
        self,
        admission_id: uuid.UUID,
        *,
        payload: Dict[str, Any],
        acknowledged: List[Dict[str, Any]],
        user: User,
    ) -> MedicationOrder:
        admission = await self._admission(admission_id, lock=True)
        if admission.status not in ACTIVE_ADMISSION:
            raise DrugChartError(
                "This patient has been discharged. Nothing new can be prescribed on this admission.",
                status_code=409,
            )

        frequency = rules.normalise_frequency(payload.get("frequency_code")) or "OD"
        is_sos = bool(payload.get("is_sos")) or frequency in rules.AS_NEEDED
        is_stat = bool(payload.get("is_stat")) or frequency in rules.ONCE
        if is_sos and is_stat:
            raise DrugChartError(
                "A medicine is given either once now (STAT) or when needed (SOS), not both."
            )
        try:
            times = [] if (is_sos or is_stat) else rules.clock_times(
                frequency, payload.get("schedule_times") or []
            )
        except rules.ScheduleError as exc:
            raise DrugChartError(str(exc)) from exc

        result = await self.check(admission_id, drug_name=payload.get("drug_name", ""))
        acknowledged_keys = {
            (item.get("kind"), tuple(sorted(item.get("medicines") or [])))
            for item in acknowledged or []
        }
        unacknowledged = [
            alert for alert in result["alerts"]
            if alert["severity"] == "serious"
            and (alert["kind"], tuple(sorted(alert["medicines"]))) not in acknowledged_keys
        ]
        if unacknowledged:
            raise DrugChartError(
                "Acknowledge the serious safety alert before prescribing — "
                + "; ".join(alert["description"] for alert in unacknowledged[:3]),
                status_code=409,
                alerts=unacknowledged,
            )

        now = _now()
        order = MedicationOrder(
            admission_id=admission_id,
            drug_name=str(payload["drug_name"]).strip(),
            generic_name=payload.get("generic_name"),
            strength=payload.get("strength"),
            dose=str(payload["dose"]).strip(),
            route=payload.get("route") or MedicationRouteIPD.ORAL,
            frequency_code="SOS" if is_sos else "STAT" if is_stat else frequency,
            schedule_times=[moment.strftime("%H:%M") for moment in times],
            status=MedicationStatus.ACTIVE,
            started_at=now,
            is_stat=is_stat,
            is_sos=is_sos,
            instructions=payload.get("instructions"),
            ordered_by_name=user.full_name,
        )
        self.session.add(order)
        await self.session.flush()

        if is_stat:
            self.session.add(MedicationAdministration(order_id=order.id, due_at=now))
        else:
            await self._top_up(order, now, existing=[])

        await self.session.commit()
        logger.info(
            "medication_ordered",
            extra={"admission": admission.ip_number, "drug": order.drug_name,
                   "frequency": order.frequency_code, "by": user.full_name,
                   "acknowledged_alerts": len(acknowledged or [])},
        )
        return await self._reload(order.id)

    # ---------------------------------------------------------- scheduling
    async def _top_up(
        self,
        order: MedicationOrder,
        now: datetime,
        *,
        existing: Optional[List[datetime]] = None,
    ) -> int:
        """Lay out any doses not yet scheduled, up to the horizon."""
        if order.status != MedicationStatus.ACTIVE or order.is_sos or order.is_stat:
            return 0
        times = [moment for moment in (rules.parse_clock(v) for v in order.schedule_times or []) if moment]
        if not times:
            try:
                times = rules.clock_times(order.frequency_code, [])
            except rules.ScheduleError:
                return 0
        if existing is None:
            existing = list(
                (
                    await self.session.execute(
                        select(MedicationAdministration.due_at).where(
                            MedicationAdministration.order_id == order.id
                        )
                    )
                ).scalars()
            )
        start = (max(existing) + timedelta(minutes=1)) if existing else order.started_at
        start = max(start, now - rules.MAX_BACKFILL)
        known = set(existing)
        added = 0
        for moment in rules.due_moments(times, start=start, until=now + rules.SCHEDULE_HORIZON):
            if moment not in known:
                self.session.add(MedicationAdministration(order_id=order.id, due_at=moment))
                added += 1
        return added

    async def chart(self, admission_id: uuid.UUID, on: date) -> Dict[str, Any]:
        """One day of the drug chart: every order, and its doses that day."""
        admission = await self._admission(admission_id)
        now = _now()

        active = (
            await self.session.execute(
                select(MedicationOrder).where(
                    MedicationOrder.admission_id == admission_id,
                    MedicationOrder.status == MedicationStatus.ACTIVE,
                )
            )
        ).scalars().all()
        added = 0
        for order in active:
            added += await self._top_up(order, now)
        if added:
            await self.session.commit()

        start, end = day_bounds(on)
        orders = (
            await self.session.execute(
                select(MedicationOrder)
                .options(selectinload(MedicationOrder.administrations))
                .where(
                    MedicationOrder.admission_id == admission_id,
                    MedicationOrder.started_at < end,
                )
                .order_by(MedicationOrder.started_at)
                .execution_options(populate_existing=True)
            )
        ).scalars().all()

        summary = {"due": 0, "overdue": 0, "given": 0, "omitted": 0}
        from app.models.admission_leave import AdmissionLeave

        away = [
            (leave.started_at, leave.returned_at)
            for leave in (await self.session.execute(
                select(AdmissionLeave).where(AdmissionLeave.admission_id == admission_id)
            )).scalars()
        ]
        rows: List[Dict[str, Any]] = []
        for order in orders:
            stopped = order.stopped_at
            if order.status != MedicationStatus.ACTIVE and stopped is not None and stopped < start:
                continue
            doses = []
            for dose in sorted(order.administrations, key=lambda item: item.due_at):
                if not (start <= dose.due_at < end):
                    continue
                # Doses that fell due after the order was stopped were never
                # owed. Signed ones stay: they happened.
                if dose.was_given is None and stopped is not None and dose.due_at > stopped:
                    continue
                away_then = dose.was_given is None and any(
                    begin <= dose.due_at and (end is None or dose.due_at < end) for begin, end in away
                )
                state = "on_leave" if away_then else rules.dose_state(
                    due_at=dose.due_at, was_given=dose.was_given, now=now
                )
                if state in summary:
                    summary[state] += 1
                signable = not away_then and (order.status == MedicationStatus.ACTIVE or (
                    stopped is not None and dose.due_at <= stopped
                )) and rules.can_sign(due_at=dose.due_at, was_given=dose.was_given, now=now)
                doses.append({
                    "id": str(dose.id),
                    "due_at": dose.due_at.isoformat(),
                    "state": state,
                    "given_at": dose.given_at.isoformat() if dose.given_at else None,
                    "given_by_name": dose.given_by_name,
                    "omission_reason": dose.omission_reason,
                    "notes": dose.notes,
                    "can_sign": signable,
                })
            last_given = max(
                (item.given_at for item in order.administrations if item.was_given and item.given_at),
                default=None,
            )
            rows.append({
                "id": str(order.id),
                "drug_name": order.drug_name,
                "generic_name": order.generic_name,
                "strength": order.strength,
                "dose": order.dose,
                "route": order.route.value,
                "frequency_code": order.frequency_code,
                "schedule_times": order.schedule_times or [],
                "status": order.status.value,
                "started_at": order.started_at.isoformat(),
                "stopped_at": stopped.isoformat() if stopped else None,
                "stop_reason": order.stop_reason,
                "is_stat": order.is_stat,
                "is_sos": order.is_sos,
                "instructions": order.instructions,
                "ordered_by_name": order.ordered_by_name,
                "last_given_at": last_given.isoformat() if last_given else None,
                "doses": doses,
            })

        return {
            "on": on.isoformat(),
            "now": now.isoformat(),
            "allergies": [item for item in (admission.allergies or []) if str(item).strip()],
            "frequencies": rules.FREQUENCY_TIMES,
            "routes": [route.value for route in MedicationRouteIPD],
            "orders": rows,
            "summary": summary,
            "on_leave": any(end is None for _begin, end in away),
        }

    # ------------------------------------------------------------- signing
    async def _on_leave(self, admission_id: uuid.UUID) -> bool:
        from app.models.admission_leave import AdmissionLeave

        return (await self.session.execute(
            select(AdmissionLeave.id).where(
                AdmissionLeave.admission_id == admission_id, AdmissionLeave.returned_at.is_(None)
            ).limit(1)
        )).first() is not None

    async def administer(
        self,
        administration_id: uuid.UUID,
        *,
        was_given: bool,
        omission_reason: Optional[str],
        notes: Optional[str],
        user: User,
    ) -> MedicationAdministration:
        dose = (
            await self.session.execute(
                select(MedicationAdministration)
                .where(MedicationAdministration.id == administration_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if dose is None:
            raise DrugChartError("That dose no longer exists.", status_code=404)
        order = await self._order(dose.order_id)
        now = _now()
        if was_given and await self._on_leave(order.admission_id):
            raise DrugChartError(
                "The patient is away on leave. A dose cannot be given until they are back; "
                "record it as not given, or mark the patient returned first.",
                status_code=409,
            )

        if dose.was_given is not None:
            raise DrugChartError(
                f"This dose was already signed for by {dose.given_by_name or 'someone'} "
                f"at {_clock(dose.given_at) if dose.given_at else 'an earlier time'}.",
                status_code=409,
            )
        if order.stopped_at is not None and dose.due_at > order.stopped_at:
            raise DrugChartError(
                "This medicine was stopped before this dose was due.", status_code=409
            )
        if not rules.can_sign(due_at=dose.due_at, was_given=dose.was_given, now=now):
            raise DrugChartError(
                f"This dose is due at {_clock(dose.due_at)}. It can be signed from "
                f"{_clock(dose.due_at - rules.SIGN_EARLY)}."
            )
        reason = (omission_reason or "").strip()
        if not was_given and not reason:
            raise DrugChartError("A dose that was not given needs a reason recorded.")

        dose.was_given = was_given
        dose.given_at = now
        dose.given_by_id = user.id
        dose.given_by_name = user.full_name
        dose.omission_reason = None if was_given else reason[:255]
        dose.notes = (notes or "").strip() or None

        # A STAT order is one dose. Once it is signed — given or not — the
        # order is finished; left "active" it sat on the chart as a running
        # medicine nobody was going to give again.
        if order.is_stat and order.status == MedicationStatus.ACTIVE:
            order.status = MedicationStatus.COMPLETED
            order.stopped_at = now
            order.stop_reason = "Single dose given" if was_given else f"Single dose not given: {reason[:200]}"

        await self.session.commit()
        return dose

    async def give_as_needed(
        self, order_id: uuid.UUID, *, notes: Optional[str], user: User
    ) -> MedicationAdministration:
        """Record an SOS dose given now."""
        order = await self._order(order_id, lock=True)
        if order.status != MedicationStatus.ACTIVE:
            raise DrugChartError("This medicine has been stopped.", status_code=409)
        if not order.is_sos:
            raise DrugChartError(
                "Only a when-needed (SOS) medicine is given on demand. Sign scheduled "
                "doses on the chart."
            )
        if await self._on_leave(order.admission_id):
            raise DrugChartError("The patient is away on leave.", status_code=409)
        now = _now()
        dose = MedicationAdministration(
            order_id=order.id,
            due_at=now,
            given_at=now,
            was_given=True,
            given_by_id=user.id,
            given_by_name=user.full_name,
            notes=(notes or "").strip() or None,
        )
        self.session.add(dose)
        await self.session.commit()
        return dose

    async def stop(self, order_id: uuid.UUID, *, reason: str, user: User) -> MedicationOrder:
        order = await self._order(order_id, lock=True)
        if order.status != MedicationStatus.ACTIVE:
            raise DrugChartError("This medicine is not running.", status_code=409)
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise DrugChartError("Say why the medicine is being stopped.")
        now = _now()
        order.status = MedicationStatus.STOPPED
        order.stopped_at = now
        order.stop_reason = reason[:255]
        # Future doses of a stopped medicine are not owed. Left in place, they
        # would turn red on the chart as missed doses of a drug nobody should give.
        await self.session.execute(
            delete(MedicationAdministration).where(
                MedicationAdministration.order_id == order.id,
                MedicationAdministration.was_given.is_(None),
                MedicationAdministration.due_at > now,
            )
        )
        await self.session.commit()
        logger.info(
            "medication_stopped",
            extra={"order_id": str(order.id), "drug": order.drug_name, "by": user.full_name},
        )
        return order
