"""Medical JSON Generator — builds the canonical MedicalRecord.

Consumes structured inputs only: the slot table, extracted symptoms, and the
transcript for grounding. Regenerated every MEDICAL_JSON_EVERY_N_TURNS during
the call (cost optimization) and once at finalization.
"""
import json
from typing import Optional

from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import MedicalRecord
from app.ai.providers.base import CostLedger
from app.ai.session.memory import ConversationMemory
from app.departments import profile_for


class MedicalJSONGeneratorService(BaseAIService[MedicalRecord]):
    stage = "medical_json_generator"
    tier = "fast"
    temperature = 0.0
    max_tokens = 1400
    output_model = MedicalRecord

    async def generate(
        self, memory: ConversationMemory, *, ledger: Optional[CostLedger] = None
    ) -> MedicalRecord:
        profile = profile_for(memory.department)
        system = (
            "You are the clinical documentation model of Satya Hospital "
            f"({profile.label} department). Build the patient's structured medical "
            "record from the collected data below. Rules: never invent facts; use null/empty "
            "for anything not stated; convert weight to kilograms and height to centimeters "
            "when given in other units; numbers must be numbers, not strings. "
            "`department_specific` holds structured findings for this department "
            f"({profile.extraction_fields}). "
            "`red_flags` must include every flag listed in the input."
        )
        collected = {
            "patient": memory.patient_info,
            "slots": {k: s.value for k, s in memory.slots.items() if s.filled},
            "symptoms": memory.symptoms,
            "red_flags": memory.all_flags,
        }
        user = (
            "Collected structured data:\n"
            + json.dumps(collected, ensure_ascii=False)
            + "\n\nFull conversation for grounding (do not add anything not supported by it):\n"
            + memory.transcript_text()
        )
        return await self.run_json(
            system=system, user=user, ledger=ledger or memory.ledger, tag=str(memory.consultation_id)
        )
