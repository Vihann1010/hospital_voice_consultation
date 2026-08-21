"""Inpatient operations: admit, move, charge, discharge.

Two things in here carry real risk and are handled deliberately.

**Two patients in one bed.** Checking that a bed is vacant and then assigning
it are two steps, and between them another clerk can assign the same bed. The
bed row is therefore locked `FOR UPDATE` and re-checked under the lock, so the
second admission is refused rather than creating an impossible ward.

**Double-charging the daily accrual.** The overnight job that posts bed-days
will be run twice — after a crash, by a nervous administrator, by a cron that
fired late. Charges carry a uniqueness constraint on
(admission, category, date, source) and the accrual reads what is already
posted before writing, so running it five times posts one day's charges.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.ipd.bed_days import Occupancy, compute_bed_days
from app.ipd.early_warning import Vitals, score_news2
from app.models.emr import ServiceItem
from app.models.enums import (
    AdmissionStatus,
    AdmissionType,
    BedStatus,
    ChargeCategory,
    Department,
    DischargeType,
    MedicationStatus,
    NoteType,
)
from app.models.ipd import (
    Admission,
    AdmissionCharge,
    Bed,
    BedOccupancy,
    ClinicalNote,
    MedicationAdministration,
    MedicationOrder,
    VitalsRecord,
    Ward,
)
from app.models.patient import Patient

logger = get_logger(__name__)


class IPDError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IPDService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------ numbering
    async def _next_ip_number(self) -> str:
        """IP numbers are sequential per year.

        Reuses the shared document counter, with the same SAVEPOINT-based
        creation as invoices: a full session rollback here would expire the
        caller's objects mid-admission.
        """
        from app.models.emr import DocumentCounter

        period = f"{date.today().year}"
        result = await self.session.execute(
            select(DocumentCounter)
            .where(DocumentCounter.scope == "ip", DocumentCounter.period == period)
            .with_for_update()
        )
        counter = result.scalar_one_or_none()

        if counter is None:
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope="ip", period=period, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = None
            if counter is None:
                result = await self.session.execute(
                    select(DocumentCounter)
                    .where(DocumentCounter.scope == "ip", DocumentCounter.period == period)
                    .with_for_update()
                )
                counter = result.scalar_one()

        counter.last_value += 1
        await self.session.flush()
        return f"IP{date.today().year % 100:02d}-{counter.last_value:05d}"

    # ----------------------------------------------------------------- beds
    async def ward_board(
        self, *, department: Optional[Department] = None
    ) -> List[Dict[str, Any]]:
        """Every ward with its beds and who is in them — the ward board."""
        statement = (
            select(Ward)
            .options(selectinload(Ward.beds))
            .where(Ward.is_active.is_(True))
            .order_by(Ward.name)
        )
        if department is not None:
            statement = statement.where(
                (Ward.department == department) | (Ward.department.is_(None))
            )
        wards = list((await self.session.execute(statement)).scalars().all())

        occupied = await self.session.execute(
            select(BedOccupancy, Admission, Patient)
            .join(Admission, Admission.id == BedOccupancy.admission_id)
            .join(Patient, Patient.id == Admission.patient_id)
            .where(BedOccupancy.ended_at.is_(None))
        )
        by_bed = {
            occupancy.bed_id: {
                "admission_id": str(admission.id),
                "ip_number": admission.ip_number,
                "patient_name": patient.name,
                "uhid": patient.uhid,
                "age": patient.age,
                "gender": patient.gender.value,
                "admitted_at": admission.admitted_at.isoformat(),
                "doctor": admission.admitting_doctor_name,
                "diagnosis": admission.provisional_diagnosis,
            }
            for occupancy, admission, patient in occupied.all()
        }

        board: List[Dict[str, Any]] = []
        for ward in wards:
            beds = []
            for bed in sorted(ward.beds, key=lambda b: b.label):
                beds.append(
                    {
                        "id": str(bed.id),
                        "label": bed.label,
                        "status": bed.status.value,
                        "rate_paise": bed.rate_override_paise or ward.daily_rate_paise,
                        "oxygen": bed.is_oxygen_supported,
                        "occupant": by_bed.get(bed.id),
                    }
                )
            board.append(
                {
                    "id": str(ward.id),
                    "code": ward.code,
                    "name": ward.name,
                    "ward_type": ward.ward_type.value,
                    "department": ward.department.value if ward.department else None,
                    "daily_rate_paise": ward.daily_rate_paise,
                    "total_beds": len(beds),
                    "occupied": sum(1 for b in beds if b["occupant"] is not None),
                    "vacant": sum(1 for b in beds if b["status"] == "vacant"),
                    "beds": beds,
                }
            )
        return board

    async def _claim_bed(self, bed_id: uuid.UUID) -> Bed:
        """Take a bed under lock, refusing if it is not free.

        The lock is what makes this safe: without it, two clerks admitting at
        the same moment both see a vacant bed and both assign it.
        """
        result = await self.session.execute(
            select(Bed).where(Bed.id == bed_id).with_for_update()
        )
        bed = result.scalar_one_or_none()
        if bed is None:
            raise IPDError("Bed not found.")
        if bed.status is not BedStatus.VACANT:
            raise IPDError(
                f"Bed {bed.label} is not available — it is currently "
                f"{bed.status.value.replace('_', ' ')}."
            )

        # Belt and braces: an open occupancy means the status column is stale.
        open_occupancy = await self.session.execute(
            select(func.count())
            .select_from(BedOccupancy)
            .where(BedOccupancy.bed_id == bed_id, BedOccupancy.ended_at.is_(None))
        )
        if int(open_occupancy.scalar_one()) > 0:
            raise IPDError(f"Bed {bed.label} still has a patient assigned to it.")

        bed.status = BedStatus.OCCUPIED
        await self.session.flush()
        return bed

    # ------------------------------------------------------------ admission
    async def admit(
        self,
        *,
        patient_id: uuid.UUID,
        bed_id: uuid.UUID,
        department: Department,
        admitting_doctor_id: Optional[uuid.UUID],
        admitting_doctor_name: str,
        admission_type: AdmissionType = AdmissionType.PLANNED,
        provisional_diagnosis: Optional[str] = None,
        reason_for_admission: Optional[str] = None,
        expected_stay_days: Optional[int] = None,
        attendant_name: Optional[str] = None,
        attendant_phone: Optional[str] = None,
        attendant_relation: Optional[str] = None,
        advance_paid_paise: int = 0,
        visit_id: Optional[uuid.UUID] = None,
        admitted_by_name: str = "",
        allergies: Optional[List[str]] = None,
    ) -> Admission:
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise IPDError("Patient not found.")

        # A patient already in a bed cannot be admitted to a second one.
        existing = await self.session.execute(
            select(Admission).where(
                Admission.patient_id == patient_id,
                Admission.status.in_(
                    [AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED]
                ),
            )
        )
        active = existing.scalar_one_or_none()
        if active is not None:
            raise IPDError(
                f"This patient is already admitted under {active.ip_number}. "
                "Discharge that admission first, or use a bed transfer."
            )

        bed = await self._claim_bed(bed_id)
        ward = await self.session.get(Ward, bed.ward_id)
        if ward is None:
            raise IPDError("The ward for this bed no longer exists.")

        now = _now()
        admission = Admission(
            ip_number=await self._next_ip_number(),
            patient_id=patient_id,
            visit_id=visit_id,
            department=department,
            admitting_doctor_id=admitting_doctor_id,
            admitting_doctor_name=admitting_doctor_name,
            admission_type=admission_type,
            status=AdmissionStatus.ADMITTED,
            admitted_at=now,
            expected_stay_days=expected_stay_days,
            provisional_diagnosis=provisional_diagnosis,
            reason_for_admission=reason_for_admission,
            allergies=allergies or [],
            attendant_name=attendant_name,
            attendant_phone=attendant_phone,
            attendant_relation=attendant_relation,
            advance_paid_paise=advance_paid_paise,
        )
        self.session.add(admission)
        await self.session.flush()

        self.session.add(
            BedOccupancy(
                admission_id=admission.id,
                bed_id=bed.id,
                bed_label=bed.label,
                ward_name=ward.name,
                daily_rate_paise=bed.rate_override_paise or ward.daily_rate_paise,
                started_at=now,
                moved_by_name=admitted_by_name,
            )
        )
        await self.session.flush()

        logger.info(
            "patient_admitted",
            extra={"ip_number": admission.ip_number, "uhid": patient.uhid,
                   "ward": ward.name, "bed": bed.label},
        )
        return admission

    async def transfer(
        self,
        *,
        admission_id: uuid.UUID,
        to_bed_id: uuid.UUID,
        reason: Optional[str] = None,
        moved_by_name: str = "",
    ) -> BedOccupancy:
        """Move a patient to another bed.

        The old occupancy is closed and a new one opened at the same instant,
        so the stay has no gap and no overlap — bed-day billing depends on
        exactly one occupancy being current at any moment.
        """
        admission = await self.session.get(Admission, admission_id)
        if admission is None:
            raise IPDError("Admission not found.")
        if not admission.is_active:
            raise IPDError("This patient is no longer admitted.")

        current = await self.session.execute(
            select(BedOccupancy).where(
                BedOccupancy.admission_id == admission_id,
                BedOccupancy.ended_at.is_(None),
            )
        )
        occupancy = current.scalar_one_or_none()
        if occupancy is not None and occupancy.bed_id == to_bed_id:
            raise IPDError("The patient is already in that bed.")

        new_bed = await self._claim_bed(to_bed_id)
        ward = await self.session.get(Ward, new_bed.ward_id)
        now = _now()

        if occupancy is not None:
            occupancy.ended_at = now
            occupancy.transfer_reason = reason
            old_bed = await self.session.get(Bed, occupancy.bed_id)
            if old_bed is not None:
                # Not vacant: a bed needs cleaning before the next patient.
                old_bed.status = BedStatus.CLEANING

        moved = BedOccupancy(
            admission_id=admission_id,
            bed_id=new_bed.id,
            bed_label=new_bed.label,
            ward_name=ward.name if ward else "",
            daily_rate_paise=new_bed.rate_override_paise
            or (ward.daily_rate_paise if ward else 0),
            started_at=now,
            transfer_reason=reason,
            moved_by_name=moved_by_name,
        )
        self.session.add(moved)
        await self.session.flush()
        logger.info(
            "patient_transferred",
            extra={"ip_number": admission.ip_number, "to_bed": new_bed.label,
                   "reason": reason},
        )
        return moved

    # -------------------------------------------------------------- charges
    async def _existing_charge_keys(
        self, admission_id: uuid.UUID
    ) -> set:
        result = await self.session.execute(
            select(
                AdmissionCharge.category,
                AdmissionCharge.charged_on,
                AdmissionCharge.source_reference,
            ).where(AdmissionCharge.admission_id == admission_id)
        )
        return {(c, d, s) for c, d, s in result.all()}

    async def _admission_with_occupancies(
        self, admission_id: uuid.UUID
    ) -> Optional[Admission]:
        """Load an admission with its occupancies actually populated.

        `session.get(..., options=[selectinload(...)])` looks equivalent and is
        not: when the object is already in the session's identity map — which
        it is whenever the caller admitted or transferred earlier in the same
        request — get() returns the cached instance and quietly discards the
        options. The relationship is then unloaded, and touching it triggers a
        lazy load that fails under asyncio with MissingGreenlet.

        An explicit select is necessary but not sufficient: SQLAlchemy will
        still hand back the identity-mapped instance with its previously
        loaded collection untouched, so an occupancy added by a transfer
        earlier in the same session is missing. `populate_existing` forces the
        loaded state to be refreshed from the query.

        Getting this wrong is not a subtle failure — discharge iterates these
        occupancies to release the bed, and a stale collection leaves a
        discharged patient holding a bed forever.
        """
        result = await self.session.execute(
            select(Admission)
            .options(selectinload(Admission.occupancies))
            .where(Admission.id == admission_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def accrue_bed_charges(
        self,
        admission_id: uuid.UUID,
        *,
        up_to: Optional[datetime] = None,
        charging_hour: int = 8,
        discharge_cutoff_hour: int = 12,
        posted_by_name: str = "system",
    ) -> List[AdmissionCharge]:
        """Post bed and nursing charges for every day not already posted.

        Safe to run repeatedly: already-posted days are skipped, so a job that
        fires twice on the same morning charges the patient once.
        """
        admission = await self._admission_with_occupancies(admission_id)
        if admission is None:
            raise IPDError("Admission not found.")
        if not admission.occupancies:
            return []

        occupancies = [
            Occupancy(
                bed_id=str(o.bed_id),
                bed_label=o.bed_label,
                ward_name=o.ward_name,
                rate_paise=o.daily_rate_paise,
                started_at=o.started_at,
                ended_at=o.ended_at,
            )
            for o in admission.occupancies
        ]

        bed_days = compute_bed_days(
            occupancies,
            admitted_at=admission.admitted_at,
            discharged_at=admission.discharged_at,
            charging_hour=charging_hour,
            discharge_cutoff_hour=discharge_cutoff_hour,
            up_to=up_to,
        )

        already = await self._existing_charge_keys(admission_id)
        posted: List[AdmissionCharge] = []

        for day in bed_days:
            key = (ChargeCategory.BED, day.on, day.bed_id)
            if key in already:
                continue
            charge = AdmissionCharge(
                admission_id=admission_id,
                category=ChargeCategory.BED,
                charged_on=day.on,
                description=f"{day.ward_name} — bed {day.bed_label}",
                source_reference=day.bed_id,
                quantity=1,
                unit_rate_paise=day.rate_paise,
                total_paise=day.rate_paise,
                posted_by_name=posted_by_name,
            )
            self.session.add(charge)
            posted.append(charge)
            already.add(key)

        # Nursing accrues per day at the ward's rate, alongside the bed.
        ward_rates: Dict[str, int] = {}
        for occupancy in admission.occupancies:
            bed = await self.session.get(Bed, occupancy.bed_id)
            if bed is not None:
                ward = await self.session.get(Ward, bed.ward_id)
                if ward is not None and ward.nursing_rate_paise:
                    ward_rates[str(occupancy.bed_id)] = ward.nursing_rate_paise

        for day in bed_days:
            rate = ward_rates.get(day.bed_id, 0)
            if not rate:
                continue
            key = (ChargeCategory.NURSING, day.on, day.bed_id)
            if key in already:
                continue
            charge = AdmissionCharge(
                admission_id=admission_id,
                category=ChargeCategory.NURSING,
                charged_on=day.on,
                description=f"Nursing care — {day.ward_name}",
                source_reference=day.bed_id,
                quantity=1,
                unit_rate_paise=rate,
                total_paise=rate,
                posted_by_name=posted_by_name,
            )
            self.session.add(charge)
            posted.append(charge)
            already.add(key)

        await self.session.flush()
        if posted:
            logger.info(
                "bed_charges_accrued",
                extra={"admission_id": str(admission_id), "posted": len(posted)},
            )
        return posted

    async def post_charge(
        self,
        *,
        admission_id: uuid.UUID,
        category: ChargeCategory,
        description: str,
        unit_rate_paise: Optional[int] = None,
        quantity: int = 1,
        service_item_id: Optional[uuid.UUID] = None,
        service_code: Optional[str] = None,
        source_reference: str = "",
        charged_on: Optional[date] = None,
        posted_by_name: str = "",
        notes: Optional[str] = None,
    ) -> AdmissionCharge:
        """Post a one-off charge — a procedure, an investigation, a consumable."""
        admission = await self.session.get(Admission, admission_id)
        if admission is None:
            raise IPDError("Admission not found.")
        if admission.status is AdmissionStatus.DISCHARGED:
            raise IPDError(
                "This admission is closed. Charges cannot be added after "
                "discharge; raise a separate bill instead."
            )
        if quantity <= 0:
            raise IPDError("Quantity must be at least 1.")

        service: Optional[ServiceItem] = None
        if service_item_id is not None:
            service = await self.session.get(ServiceItem, service_item_id)
        elif service_code:
            found = await self.session.execute(
                select(ServiceItem).where(ServiceItem.code == service_code)
            )
            service = found.scalar_one_or_none()

        rate = unit_rate_paise
        if rate is None:
            if service is None:
                raise IPDError(f"No rate available for {description}.")
            rate = service.rate_paise
        if rate < 0:
            raise IPDError("A negative rate is not valid.")

        charge = AdmissionCharge(
            admission_id=admission_id,
            category=category,
            charged_on=charged_on or date.today(),
            description=description or (service.name if service else ""),
            source_reference=source_reference or str(uuid.uuid4())[:8],
            service_item_id=service.id if service else None,
            quantity=quantity,
            unit_rate_paise=rate,
            total_paise=rate * quantity,
            tax_percent=service.tax_percent if service else 0,
            posted_by_name=posted_by_name,
            notes=notes,
        )
        self.session.add(charge)
        await self.session.flush()
        return charge

    async def running_bill(self, admission_id: uuid.UUID) -> Dict[str, Any]:
        """What the stay has cost so far, grouped the way families ask."""
        admission = await self.session.get(Admission, admission_id)
        if admission is None:
            raise IPDError("Admission not found.")

        result = await self.session.execute(
            select(
                AdmissionCharge.category,
                func.count(AdmissionCharge.id),
                func.coalesce(func.sum(AdmissionCharge.total_paise), 0),
            )
            .where(AdmissionCharge.admission_id == admission_id)
            .group_by(AdmissionCharge.category)
        )
        rows = result.all()
        by_category = {
            category.value: {"count": int(count), "total_paise": int(total or 0)}
            for category, count, total in rows
        }
        total = sum(item["total_paise"] for item in by_category.values())

        return {
            "admission_id": str(admission_id),
            "ip_number": admission.ip_number,
            "by_category": by_category,
            "total_paise": total,
            "advance_paid_paise": admission.advance_paid_paise,
            "balance_paise": total - admission.advance_paid_paise,
            "days_so_far": by_category.get("bed", {}).get("count", 0),
        }

    # --------------------------------------------------------------- vitals
    async def record_vitals(
        self,
        *,
        admission_id: uuid.UUID,
        recorded_by_id: Optional[uuid.UUID],
        recorded_by_name: str,
        respiratory_rate: Optional[int] = None,
        spo2_percent: Optional[int] = None,
        on_oxygen: bool = False,
        oxygen_litres: Optional[float] = None,
        systolic_bp: Optional[int] = None,
        diastolic_bp: Optional[int] = None,
        pulse: Optional[int] = None,
        temperature_c: Optional[float] = None,
        consciousness: Optional[str] = None,
        spo2_scale_2: bool = False,
        pain_score: Optional[int] = None,
        blood_sugar_mgdl: Optional[int] = None,
        urine_output_ml: Optional[int] = None,
    ) -> Tuple[VitalsRecord, Dict[str, Any]]:
        """Record observations and score them.

        Scoring happens here, on write, and the result is stored on the row —
        so the number a nurse saw and acted on is preserved even if the
        scoring rules are revised later.
        """
        admission = await self.session.get(Admission, admission_id)
        if admission is None:
            raise IPDError("Admission not found.")

        score = score_news2(
            Vitals(
                respiratory_rate=respiratory_rate,
                spo2_percent=spo2_percent,
                on_oxygen=on_oxygen,
                systolic_bp=systolic_bp,
                pulse=pulse,
                temperature_c=temperature_c,
                consciousness=consciousness,
                spo2_scale_2=spo2_scale_2,
            )
        )

        record = VitalsRecord(
            admission_id=admission_id,
            recorded_at=_now(),
            recorded_by_id=recorded_by_id,
            recorded_by_name=recorded_by_name,
            respiratory_rate=respiratory_rate,
            spo2_percent=spo2_percent,
            on_oxygen=on_oxygen,
            oxygen_litres=oxygen_litres,
            systolic_bp=systolic_bp,
            diastolic_bp=diastolic_bp,
            pulse=pulse,
            temperature_c=temperature_c,
            consciousness=consciousness,
            spo2_scale_2=spo2_scale_2,
            pain_score=pain_score,
            blood_sugar_mgdl=blood_sugar_mgdl,
            urine_output_ml=urine_output_ml,
            news2_score=score.total,
            news2_risk=score.risk,
            news2_detail={
                "parameters": [
                    {"parameter": p.parameter, "value": p.value, "score": p.score}
                    for p in score.parameters
                ],
                "missing": score.missing,
                "highest_single": score.highest_single,
                "red_score": score.red_score,
                "response": score.response,
                "monitoring": score.monitoring,
            },
        )
        self.session.add(record)
        await self.session.flush()

        if score.risk in ("high", "critical") or score.red_score:
            logger.warning(
                "early_warning_escalation",
                extra={"admission_id": str(admission_id), "ip_number": admission.ip_number,
                       "news2": score.total, "risk": score.risk},
            )

        return record, {
            "total": score.total,
            "risk": score.risk,
            "response": score.response,
            "monitoring": score.monitoring,
            "red_score": score.red_score,
            "missing": score.missing,
        }

    async def deteriorating_patients(
        self, *, department: Optional[Department] = None, threshold: int = 5
    ) -> List[Dict[str, Any]]:
        """Everyone currently scoring at or above the escalation threshold.

        This is the ward's safety net: one query that answers "who is in
        trouble right now" across every bed.
        """
        latest = (
            select(
                VitalsRecord.admission_id,
                func.max(VitalsRecord.recorded_at).label("latest"),
            )
            .group_by(VitalsRecord.admission_id)
            .subquery()
        )
        statement = (
            select(VitalsRecord, Admission, Patient)
            .join(
                latest,
                and_(
                    VitalsRecord.admission_id == latest.c.admission_id,
                    VitalsRecord.recorded_at == latest.c.latest,
                ),
            )
            .join(Admission, Admission.id == VitalsRecord.admission_id)
            .join(Patient, Patient.id == Admission.patient_id)
            .where(
                Admission.status.in_(
                    [AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED]
                ),
                VitalsRecord.news2_score >= threshold,
            )
            .order_by(VitalsRecord.news2_score.desc())
        )
        if department is not None:
            statement = statement.where(Admission.department == department)

        rows = (await self.session.execute(statement)).all()
        out = []
        for vitals, admission, patient in rows:
            occupancy = await self.session.execute(
                select(BedOccupancy).where(
                    BedOccupancy.admission_id == admission.id,
                    BedOccupancy.ended_at.is_(None),
                )
            )
            bed = occupancy.scalar_one_or_none()
            out.append(
                {
                    "admission_id": str(admission.id),
                    "ip_number": admission.ip_number,
                    "patient_name": patient.name,
                    "uhid": patient.uhid,
                    "ward": bed.ward_name if bed else "",
                    "bed": bed.bed_label if bed else "",
                    "news2_score": vitals.news2_score,
                    "risk": vitals.news2_risk,
                    "recorded_at": vitals.recorded_at.isoformat(),
                    "response": (vitals.news2_detail or {}).get("response", ""),
                }
            )
        return out

    # ------------------------------------------------------------ discharge
    async def initiate_discharge(
        self, admission_id: uuid.UUID, *, final_diagnosis: Optional[str] = None
    ) -> Admission:
        """Mark the patient for discharge without freeing the bed.

        The bed stays occupied until the bill is settled and the patient
        physically leaves — releasing it here would let the ward assign a bed
        that still has someone in it.
        """
        admission = await self.session.get(Admission, admission_id)
        if admission is None:
            raise IPDError("Admission not found.")
        if admission.status is not AdmissionStatus.ADMITTED:
            raise IPDError("This admission is not in a state that can be discharged.")

        admission.status = AdmissionStatus.DISCHARGE_INITIATED
        if final_diagnosis:
            admission.final_diagnosis = final_diagnosis
        await self.session.flush()
        return admission

    async def complete_discharge(
        self,
        admission_id: uuid.UUID,
        *,
        discharge_type: DischargeType = DischargeType.ROUTINE,
        final_diagnosis: Optional[str] = None,
        discharged_by_name: str = "",
        charging_hour: int = 8,
        discharge_cutoff_hour: int = 12,
    ) -> Tuple[Admission, Dict[str, Any]]:
        """Close the stay: final accrual, free the bed, stop medications."""
        admission = await self._admission_with_occupancies(admission_id)
        if admission is None:
            raise IPDError("Admission not found.")
        if admission.status is AdmissionStatus.DISCHARGED:
            raise IPDError("This patient has already been discharged.")

        now = _now()
        admission.discharged_at = now
        admission.status = AdmissionStatus.DISCHARGED
        admission.discharge_type = discharge_type
        if final_diagnosis:
            admission.final_diagnosis = final_diagnosis
        await self.session.flush()

        # Accrue after setting discharged_at, so the cut-off rule applies to
        # the final day.
        await self.accrue_bed_charges(
            admission_id,
            charging_hour=charging_hour,
            discharge_cutoff_hour=discharge_cutoff_hour,
            posted_by_name=discharged_by_name or "system",
        )

        for occupancy in admission.occupancies:
            if occupancy.ended_at is None:
                occupancy.ended_at = now
                bed = await self.session.get(Bed, occupancy.bed_id)
                if bed is not None:
                    bed.status = BedStatus.CLEANING

        active_meds = await self.session.execute(
            select(MedicationOrder).where(
                MedicationOrder.admission_id == admission_id,
                MedicationOrder.status == MedicationStatus.ACTIVE,
            )
        )
        for order in active_meds.scalars().all():
            order.status = MedicationStatus.COMPLETED
            order.stopped_at = now
            order.stop_reason = "Patient discharged"

        await self.session.flush()
        bill = await self.running_bill(admission_id)

        logger.info(
            "patient_discharged",
            extra={"ip_number": admission.ip_number, "type": discharge_type.value,
                   "total_paise": bill["total_paise"]},
        )
        return admission, bill

    # -------------------------------------------------------------- reading
    async def get_admission(self, admission_id: uuid.UUID) -> Optional[Admission]:
        result = await self.session.execute(
            select(Admission)
            .options(
                selectinload(Admission.occupancies),
                selectinload(Admission.charges),
                selectinload(Admission.vitals),
                selectinload(Admission.notes),
                selectinload(Admission.medications).selectinload(
                    MedicationOrder.administrations
                ),
            )
            .where(Admission.id == admission_id)
        )
        return result.scalar_one_or_none()

    async def active_admissions(
        self, *, department: Optional[Department] = None
    ) -> List[Admission]:
        statement = (
            select(Admission)
            .where(
                Admission.status.in_(
                    [AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED]
                )
            )
            .order_by(Admission.admitted_at.desc())
        )
        if department is not None:
            statement = statement.where(Admission.department == department)
        return list((await self.session.execute(statement)).scalars().all())

    async def census(self, *, on: Optional[date] = None) -> Dict[str, Any]:
        """Beds occupied, free and out of service — the number management asks for."""
        beds = await self.session.execute(
            select(Bed.status, func.count()).group_by(Bed.status)
        )
        by_status = {status.value: int(count) for status, count in beds.all()}
        total = sum(by_status.values())
        occupied = by_status.get(BedStatus.OCCUPIED.value, 0)

        admitted = await self.session.execute(
            select(func.count())
            .select_from(Admission)
            .where(
                Admission.status.in_(
                    [AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED]
                )
            )
        )
        today = on or date.today()
        admissions_today = await self.session.execute(
            select(func.count())
            .select_from(Admission)
            .where(func.date(Admission.admitted_at) == today)
        )
        discharges_today = await self.session.execute(
            select(func.count())
            .select_from(Admission)
            .where(func.date(Admission.discharged_at) == today)
        )
        return {
            "on": today.isoformat(),
            "total_beds": total,
            "occupied": occupied,
            "vacant": by_status.get(BedStatus.VACANT.value, 0),
            "cleaning": by_status.get(BedStatus.CLEANING.value, 0),
            "out_of_service": by_status.get(BedStatus.BLOCKED.value, 0)
            + by_status.get(BedStatus.MAINTENANCE.value, 0),
            "occupancy_percent": round(occupied / total * 100, 1) if total else 0.0,
            "current_inpatients": int(admitted.scalar_one()),
            "admissions_today": int(admissions_today.scalar_one()),
            "discharges_today": int(discharges_today.scalar_one()),
            "by_status": by_status,
        }
