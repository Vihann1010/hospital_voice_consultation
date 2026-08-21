import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.consultation import Consultation, ConversationTurn
from app.models.enums import ConsultationStatus, Department, TurnRole
from app.models.patient import Patient
from app.repositories.base import BaseRepository


class ConsultationRepository(BaseRepository[Consultation]):
    model = Consultation

    async def get_with_details(self, consultation_id: uuid.UUID) -> Optional[Consultation]:
        result = await self.session.execute(
            select(Consultation)
            .options(selectinload(Consultation.patient), selectinload(Consultation.turns))
            .where(Consultation.id == consultation_id)
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        department: Optional[Department] = None,
        status: Optional[ConsultationStatus] = None,
        query: Optional[str] = None,
        patient_id: Optional[uuid.UUID] = None,
        reviewed: Optional[bool] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[Sequence[Consultation], int]:
        """Dashboard listing: filter by department, status, patient, or free text."""
        statement = select(Consultation).options(selectinload(Consultation.patient))
        count_statement = select(func.count()).select_from(Consultation)
        conditions = []
        if department is not None:
            conditions.append(Consultation.department == department)
        if status is not None:
            conditions.append(Consultation.status == status)
        if patient_id is not None:
            conditions.append(Consultation.patient_id == patient_id)
        if reviewed is not None:
            # The doctor's sign-off lives in the dossier JSONB; a NULL dossier
            # or a missing key both mean "not yet seen".
            marker = Consultation.medical_json.op("->>")("reviewed_at")
            conditions.append(marker.isnot(None) if reviewed else marker.is_(None))
        if query and query.strip():
            term = f"%{query.strip()}%"
            statement = statement.join(Patient, Consultation.patient_id == Patient.id)
            count_statement = count_statement.join(
                Patient, Consultation.patient_id == Patient.id
            )
            conditions.append(or_(Patient.name.ilike(term), Patient.phone_number.ilike(term)))
        for condition in conditions:
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        statement = statement.order_by(Consultation.started_at.desc()).offset(offset).limit(limit)
        rows = await self.session.execute(statement)
        total = await self.session.execute(count_statement)
        return rows.scalars().all(), int(total.scalar_one())

    async def count_waiting(self, *, department: Optional[Department] = None) -> int:
        """Intake finished but the doctor has not signed off yet."""
        statement = (
            select(func.count())
            .select_from(Consultation)
            .where(
                Consultation.status == ConsultationStatus.COMPLETED,
                Consultation.medical_json.op("->>")("reviewed_at").is_(None),
            )
        )
        if department is not None:
            statement = statement.where(Consultation.department == department)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def mark_reviewed(
        self, consultation_id: uuid.UUID, *, doctor_id: uuid.UUID, doctor_name: str
    ) -> Optional[Consultation]:
        consultation = await self.get(consultation_id)
        if consultation is None:
            return None
        dossier = dict(consultation.medical_json or {})
        dossier["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        dossier["reviewed_by"] = {"id": str(doctor_id), "name": doctor_name}
        consultation.medical_json = dossier
        await self.session.flush()
        return consultation

    async def counts_by_status(
        self, *, department: Optional[Department] = None
    ) -> Dict[str, int]:
        """Live tile counts for the dashboard header."""
        statement = select(Consultation.status, func.count(Consultation.id)).group_by(
            Consultation.status
        )
        if department is not None:
            statement = statement.where(Consultation.department == department)
        rows = await self.session.execute(statement)
        counts = {status.value: 0 for status in ConsultationStatus}
        for status, count in rows.all():
            counts[status.value] = int(count)

        since = datetime.now(timezone.utc) - timedelta(hours=24)
        today_statement = select(func.count()).select_from(Consultation).where(
            Consultation.started_at >= since
        )
        if department is not None:
            today_statement = today_statement.where(Consultation.department == department)
        today = await self.session.execute(today_statement)
        counts["last_24h"] = int(today.scalar_one())
        counts["waiting"] = await self.count_waiting(department=department)
        return counts

    async def next_turn_sequence(self, consultation_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(ConversationTurn.sequence), 0)).where(
                ConversationTurn.consultation_id == consultation_id
            )
        )
        return int(result.scalar_one()) + 1

    async def add_turn(
        self,
        *,
        consultation_id: uuid.UUID,
        role: TurnRole,
        content: str,
        interrupted: bool = False,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            consultation_id=consultation_id,
            role=role,
            content=content,
            sequence=await self.next_turn_sequence(consultation_id),
            interrupted=interrupted,
        )
        self.session.add(turn)
        await self.session.flush()
        return turn

    async def get_turns(self, consultation_id: uuid.UUID) -> List[ConversationTurn]:
        result = await self.session.execute(
            select(ConversationTurn)
            .where(ConversationTurn.consultation_id == consultation_id)
            .order_by(ConversationTurn.sequence)
        )
        return list(result.scalars().all())
