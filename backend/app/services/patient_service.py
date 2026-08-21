"""Patient directory and longitudinal history for the doctor dashboard."""
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation import Consultation
from app.models.patient import Patient
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.patient_repository import PatientRepository


class PatientService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.patients = PatientRepository(session)
        self.consultations = ConsultationRepository(session)

    async def search(
        self, *, query: Optional[str], offset: int = 0, limit: int = 25, department=None
    ) -> Tuple[Sequence[Patient], int, Dict[uuid.UUID, int]]:
        patients, total = await self.patients.search(
            query=query, offset=offset, limit=limit, department=department
        )
        counts = await self.patients.visit_counts([p.id for p in patients])
        return patients, total, counts

    async def get(self, patient_id: uuid.UUID) -> Optional[Patient]:
        return await self.patients.get(patient_id)

    async def history(self, patient_id: uuid.UUID, *, department=None) -> List[Consultation]:
        return await self.patients.consultations_for(patient_id, department=department)

    @staticmethod
    def aggregate_history(consultations: List[Consultation]) -> Dict[str, Any]:
        """Roll every past visit into the standing clinical picture.

        Medicines, allergies, conditions and surgeries accumulate across visits;
        the most recent mention wins for display order. This is what the doctor
        sees as "known about this patient" before reading today's notes.
        """
        medicines: Dict[str, Dict[str, Any]] = {}
        allergies: Dict[str, str] = {}
        conditions: Dict[str, str] = {}
        surgeries: Dict[str, Dict[str, Any]] = {}

        for consultation in consultations:  # newest first
            dossier = consultation.medical_json or {}
            record = dossier.get("medical_json") or {}
            visit = {
                "consultation_id": str(consultation.id),
                "date": consultation.started_at.isoformat() if consultation.started_at else None,
            }
            for item in record.get("current_medicines") or []:
                if isinstance(item, dict) and item.get("name"):
                    key = str(item["name"]).strip().lower()
                    medicines.setdefault(
                        key,
                        {
                            "name": item["name"],
                            "dose_or_frequency": item.get("dose_or_frequency"),
                            "first_seen": visit,
                        },
                    )
            for allergy in record.get("allergies") or []:
                if str(allergy).strip():
                    allergies.setdefault(str(allergy).strip().lower(), str(allergy).strip())
            for condition in record.get("medical_history") or []:
                if str(condition).strip():
                    conditions.setdefault(str(condition).strip().lower(), str(condition).strip())
            for surgery in record.get("previous_surgeries") or []:
                if isinstance(surgery, dict) and surgery.get("name"):
                    key = str(surgery["name"]).strip().lower()
                    surgeries.setdefault(
                        key,
                        {"name": surgery["name"], "year_or_when": surgery.get("year_or_when")},
                    )

        return {
            "current_medicines": list(medicines.values()),
            "allergies": list(allergies.values()),
            "conditions": list(conditions.values()),
            "previous_surgeries": list(surgeries.values()),
            "total_visits": len(consultations),
        }
