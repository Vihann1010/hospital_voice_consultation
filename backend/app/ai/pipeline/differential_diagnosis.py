"""Differential Diagnosis Generator — decision support for the doctor.

Explicitly framed as clinician decision support: ranked possibilities with
supporting/contradicting features and what would discriminate between them.
Never shown to the patient; the disclaimer travels inside the schema.
"""
import json
from typing import Optional

from app.core.config import settings
from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import ClinicalSummary, DifferentialDiagnosis, MedicalRecord, RiskAssessment
from app.ai.providers.base import CostLedger
from app.ai.session.memory import ConversationMemory


class DifferentialDiagnosisService(BaseAIService[DifferentialDiagnosis]):
    stage = "differential_diagnosis"
    tier = "dialogue"
    temperature = 0.2
    max_tokens = 1100
    output_model = DifferentialDiagnosis

    async def generate(
        self,
        memory: ConversationMemory,
        record: MedicalRecord,
        risk: RiskAssessment,
        summary: ClinicalSummary,
        *,
        ledger: Optional[CostLedger] = None,
    ) -> DifferentialDiagnosis:
        system = (
            f"You are a clinical decision-support model assisting a specialist at "
            f"{settings.brand_for(memory.department)}"
            f"Hospital ({memory.department.value}). Produce 3-5 differentials appropriate to "
            "this department and patient demographics, ordered by likelihood. Ground every "
            "supporting/contradicting feature in the record — cite the actual finding, not a "
            "textbook generality. `would_change_with` names the examination finding or test "
            "that would most efficiently confirm or exclude that differential. If red flags "
            "exist, the dangerous diagnosis to exclude comes first regardless of likelihood."
        )
        user = (
            f"Patient: {json.dumps(memory.patient_info, ensure_ascii=False)}\n"
            f"Medical record:\n{record.model_dump_json()}\n"
            f"Risk:\n{risk.model_dump_json()}\n"
            f"Summary:\n{summary.model_dump_json()}"
        )
        return await self.run_json(
            system=system, user=user, ledger=ledger or memory.ledger, tag=str(memory.consultation_id)
        )
