import uuid
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select

from app.models.consultation import Consultation
from app.models.patient import Patient
from app.repositories.base import BaseRepository


class PatientRepository(BaseRepository[Patient]):
    model = Patient

    async def find_returning_patient(self, phone_number: str, name: str) -> Optional[Patient]:
        """Match an existing record so repeat visits don't duplicate patients."""
        result = await self.session.execute(
            select(Patient)
            .where(Patient.phone_number == phone_number, Patient.name.ilike(name))
            .order_by(Patient.created_at.desc())
            .limit(1)
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

        With `department`, only patients who have attended that department are
        returned, so a consultant's directory matches their consultation list.
        """
        statement = select(Patient)
        count_statement = select(func.count()).select_from(Patient)
        if department is not None:
            attended = (
                select(Consultation.patient_id)
                .where(Consultation.department == department)
                .distinct()
                .scalar_subquery()
            )
            statement = statement.where(Patient.id.in_(attended))
            count_statement = count_statement.where(Patient.id.in_(attended))
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
        """Visit count per patient, for list views (avoids an N+1 query)."""
        if not patient_ids:
            return {}
        result = await self.session.execute(
            select(Consultation.patient_id, func.count(Consultation.id))
            .where(Consultation.patient_id.in_(list(patient_ids)))
            .group_by(Consultation.patient_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

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
