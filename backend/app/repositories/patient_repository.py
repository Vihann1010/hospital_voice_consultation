import uuid
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.consultation import Consultation
from app.models.emr import Visit
from app.models.patient import Patient
from app.repositories.base import BaseRepository


class PatientRepository(BaseRepository[Patient]):
    model = Patient

    async def find_returning_patient(
        self, phone_number: str, name: str, *, practice: Optional[str] = None,
        default_practice: Optional[str] = None,
    ) -> Optional[Patient]:
        """Match an existing record so repeat visits don't duplicate patients.

        Within one practice only: a dental walk-in with the same phone as a
        gastro patient is a new Smile Dental patient, not the gastro record.
        A record with no practice is the site default's.
        """
        statement = select(Patient).where(
            Patient.phone_number == phone_number, Patient.name.ilike(name)
        )
        if practice is not None:
            if practice == default_practice:
                statement = statement.where(
                    (Patient.practice == practice) | (Patient.practice.is_(None))
                )
            else:
                statement = statement.where(Patient.practice == practice)
        result = await self.session.execute(
            statement.order_by(Patient.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        query: Optional[str] = None,
        offset: int = 0,
        limit: int = 25,
        department=None,
    ) -> Tuple[Sequence[Patient], int]:
        """Free-text search across name and phone number.

        With `department`, only patients who have registered a visit for that
        department are returned, including patients awaiting voice intake.
        """
        statement = select(Patient)
        count_statement = select(func.count()).select_from(Patient)
        if department is not None:
            registered = (
                select(Visit.patient_id)
                .where(Visit.department == department)
                .distinct()
                .scalar_subquery()
            )
            statement = statement.where(Patient.id.in_(registered))
            count_statement = count_statement.where(Patient.id.in_(registered))
        if query and query.strip():
            term = f"%{query.strip()}%"
            condition = or_(Patient.name.ilike(term), Patient.phone_number.ilike(term))
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        statement = statement.order_by(Patient.created_at.desc()).offset(offset).limit(limit)
        rows = await self.session.execute(statement)
        total = await self.session.execute(count_statement)
        return rows.scalars().all(), int(total.scalar_one())

    async def visit_counts(self, patient_ids: Sequence[uuid.UUID]) -> dict:
        """Reception visit summaries for list views (avoids N+1 queries)."""
        if not patient_ids:
            return {}
        result = await self.session.execute(
            select(Visit.patient_id, func.count(Visit.id))
            .where(Visit.patient_id.in_(list(patient_ids)))
            .group_by(Visit.patient_id)
        )
        counts = {row[0]: int(row[1]) for row in result.all()}
        latest_result = await self.session.execute(
            select(Visit)
            .options(selectinload(Visit.invoices))
            .where(Visit.patient_id.in_(list(patient_ids)))
            .order_by(Visit.created_at.desc())
        )
        summaries = {}
        for visit in latest_result.scalars().all():
            if visit.patient_id in summaries:
                continue
            invoice = max(visit.invoices, key=lambda item: item.created_at) if visit.invoices else None
            summaries[visit.patient_id] = {
                "visit_count": counts.get(visit.patient_id, 0),
                "visit_reason": visit.notes or visit.visit_type.value.replace("_", " ").title(),
                "payment_status": invoice.status.value if invoice else "not_billed",
            }
        return summaries

    async def consultations_for(
        self, patient_id: uuid.UUID, *, department=None
    ) -> List[Consultation]:
        """Full visit history, newest first — the patient timeline.

        Scoped to one department when given, so a consultant does not see
        visits made to the other specialty.
        """
        statement = (
            select(Consultation)
            .where(Consultation.patient_id == patient_id)
            .order_by(Consultation.started_at.desc())
        )
        if department is not None:
            statement = statement.where(Consultation.department == department)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
