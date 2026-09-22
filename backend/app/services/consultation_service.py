"""Consultation lifecycle: intake, turn persistence, finalization."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_consultation_token
from app.models.consultation import Consultation, ConversationTurn
from app.models.enums import ConsultationStatus, Department, TurnRole, VisitType
from app.models.patient import Patient
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.schemas import (
    ConsultationStartRequest,
    ConsultationStartResponse,
)

logger = get_logger(__name__)


class ConsultationError(Exception):
    """A consultation cannot be started or advanced. The message is shown to
    staff, so it says what to do rather than what went wrong internally."""


class ConsultationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.patients = PatientRepository(session)
        self.consultations = ConsultationRepository(session)

    # -- intake -------------------------------------------------------------
    async def start_from_visit(self, visit_id: uuid.UUID) -> ConsultationStartResponse:
        """Begin voice intake for a visit reception already registered.

        The patient, department and demographics come from the visit, so
        nothing is re-typed and no duplicate patient record is created. The
        visit is moved to in_consultation and linked to the consultation, so
        the front desk sees who has gone in.
        """
        from app.models.emr import Visit
        from app.models.enums import VisitStatus, VisitType

        visit = await self.session.get(Visit, visit_id)
        if visit is None:
            raise ConsultationError("That registration could not be found.")
        if visit.visit_type is not VisitType.NEW:
            raise ConsultationError("Only new OPD visits can start voice intake.")
        if visit.consultation_id is not None:
            raise ConsultationError(
                "Voice intake has already been started for this patient."
            )
        if visit.status is not VisitStatus.REGISTERED:
            raise ConsultationError("This visit is not waiting for voice intake.")

        patient = await self.session.get(Patient, visit.patient_id)
        if patient is None:
            raise ConsultationError("The patient record for this visit is missing.")

        consultation = await self.consultations.add(
            Consultation(
                patient_id=patient.id,
                department=visit.department,
                status=ConsultationStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc),
            )
        )

        visit.consultation_id = consultation.id
        visit.status = VisitStatus.IN_CONSULTATION
        await self.session.flush()

        token = create_consultation_token(
            consultation_id=consultation.id, patient_id=patient.id
        )
        logger.info(
            "consultation_started_from_visit",
            extra={
                "consultation_id": str(consultation.id),
                "visit": visit.visit_number,
                "uhid": patient.uhid,
                "department": visit.department.value,
            },
        )
        return ConsultationStartResponse(
            consultation_id=consultation.id,
            patient_id=patient.id,
            department=visit.department,
            session_token=token,
            ws_path=f"{settings.API_V1_PREFIX}/ws/consultations/{consultation.id}",
        )

    async def restart_from_consultation(
        self, consultation_id: uuid.UUID
    ) -> ConsultationStartResponse:
        """Replace a voice session while keeping the registered visit intact."""
        from app.models.emr import Visit
        from app.models.enums import VisitStatus

        consultation = await self.consultations.get(consultation_id)
        if consultation is None:
            raise ConsultationError("That consultation could not be found.")
        visit_result = await self.session.execute(
            select(Visit).where(Visit.consultation_id == consultation_id)
        )
        visit = visit_result.scalar_one_or_none()
        patient = await self.session.get(Patient, consultation.patient_id)
        if patient is None:
            raise ConsultationError("The patient record for this visit is missing.")

        consultation.status = ConsultationStatus.ABANDONED
        consultation.ended_at = datetime.now(timezone.utc)
        replacement = await self.consultations.add(
            Consultation(
                patient_id=patient.id,
                department=consultation.department,
                status=ConsultationStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc),
            )
        )
        if visit is not None:
            visit.consultation_id = replacement.id
            visit.status = VisitStatus.IN_CONSULTATION
        await self.session.flush()
        token = create_consultation_token(
            consultation_id=replacement.id, patient_id=patient.id
        )
        return ConsultationStartResponse(
            consultation_id=replacement.id,
            patient_id=patient.id,
            department=replacement.department,
            session_token=token,
            ws_path=f"{settings.API_V1_PREFIX}/ws/consultations/{replacement.id}",
        )

    async def start(self, payload: ConsultationStartRequest) -> ConsultationStartResponse:
        from app.practices import default_practice, for_department

        practice = for_department(payload.department)
        patient = await self.patients.find_returning_patient(
            payload.patient.phone_number, payload.patient.name,
            practice=practice.prefix, default_practice=default_practice().prefix,
        )
        if patient is None:
            patient = await self.patients.add(
                Patient(
                    practice=practice.prefix,
                    name=payload.patient.name.strip(),
                    age=payload.patient.age,
                    gender=payload.patient.gender,
                    phone_number=payload.patient.phone_number,
                )
            )
        else:
            patient.age = payload.patient.age  # keep demographics current

        consultation = await self.consultations.add(
            Consultation(
                patient_id=patient.id,
                department=payload.department,
                status=ConsultationStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc),
            )
        )
        token = create_consultation_token(consultation_id=consultation.id, patient_id=patient.id)
        logger.info(
            "consultation_started",
            extra={
                "consultation_id": str(consultation.id),
                "department": payload.department.value,
            },
        )
        return ConsultationStartResponse(
            consultation_id=consultation.id,
            patient_id=patient.id,
            department=payload.department,
            session_token=token,
            ws_path=f"{settings.API_V1_PREFIX}/ws/consultations/{consultation.id}",
        )

    # -- reads --------------------------------------------------------------
    async def get_detail(self, consultation_id: uuid.UUID) -> Optional[Consultation]:
        return await self.consultations.get_with_details(consultation_id)

    async def update_vitals(
        self, consultation_id: uuid.UUID, vitals: Dict[str, Optional[str]]
    ) -> Optional[Consultation]:
        consultation = await self.consultations.get_with_details(consultation_id)
        if consultation is None:
            return None
        dossier = dict(consultation.medical_json or {})
        dossier["vitals"] = vitals
        consultation.medical_json = dossier
        await self.session.flush()
        return consultation

    async def list(
        self,
        *,
        department=None,
        status=None,
        query: Optional[str] = None,
        patient_id: Optional[uuid.UUID] = None,
        reviewed: Optional[bool] = None,
        visit_type: Optional[VisitType] = None,
        offset: int = 0,
        limit: int = 50,
    ):
        return await self.consultations.list_paginated(
            department=department,
            status=status,
            query=query,
            patient_id=patient_id,
            reviewed=reviewed,
            visit_type=visit_type,
            offset=offset,
            limit=limit,
        )

    async def mark_reviewed(
        self, consultation_id: uuid.UUID, *, doctor_id: uuid.UUID, doctor_name: str
    ) -> Optional[Consultation]:
        consultation = await self.consultations.mark_reviewed(
            consultation_id, doctor_id=doctor_id, doctor_name=doctor_name
        )
        if consultation is not None:
            await self.session.commit()
        return consultation

    async def stats(self, *, department=None) -> dict:
        return await self.consultations.counts_by_status(department=department)

    async def get_session_context(
        self, consultation_id: uuid.UUID
    ) -> Optional[Tuple[Consultation, Patient, List[ConversationTurn]]]:
        consultation = await self.consultations.get_with_details(consultation_id)
        if consultation is None:
            return None
        return consultation, consultation.patient, list(consultation.turns)

    # -- turn persistence ----------------------------------------------------
    async def record_turn(
        self,
        *,
        consultation_id: uuid.UUID,
        role: TurnRole,
        content: str,
        interrupted: bool = False,
    ) -> ConversationTurn:
        turn = await self.consultations.add_turn(
            consultation_id=consultation_id,
            role=role,
            content=content,
            interrupted=interrupted,
        )
        await self.session.commit()
        return turn

    async def update_medical_json(
        self, consultation_id: uuid.UUID, medical_json: Dict[str, Any]
    ) -> None:
        consultation = await self.consultations.get(consultation_id)
        if consultation is not None:
            existing = consultation.medical_json or {}
            if existing.get("vitals") and "vitals" not in medical_json:
                medical_json = {**medical_json, "vitals": existing["vitals"]}
            consultation.medical_json = medical_json
            await self.session.commit()

    # -- finalization --------------------------------------------------------
    async def finalize(
        self,
        consultation_id: uuid.UUID,
        *,
        medical_json: Optional[Dict[str, Any]] = None,
        status: ConsultationStatus = ConsultationStatus.COMPLETED,
    ) -> Optional[Consultation]:
        consultation = await self.consultations.get(consultation_id)
        if consultation is None:
            return None
        turns = await self.consultations.get_turns(consultation_id)
        consultation.transcript = self.build_transcript(turns)
        if medical_json is not None:
            existing = consultation.medical_json or {}
            if existing.get("vitals") and "vitals" not in medical_json:
                medical_json = {**medical_json, "vitals": existing["vitals"]}
            consultation.medical_json = medical_json
        consultation.status = status
        consultation.ended_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info(
            "consultation_finalized",
            extra={"consultation_id": str(consultation_id), "status": status.value},
        )
        return consultation

    @staticmethod
    def build_transcript(turns: List[ConversationTurn]) -> str:
        lines = []
        for turn in turns:
            speaker = "Patient" if turn.role == TurnRole.PATIENT else "Assistant"
            suffix = " [interrupted]" if turn.interrupted else ""
            lines.append(f"{speaker}: {turn.content}{suffix}")
        return "\n".join(lines)
