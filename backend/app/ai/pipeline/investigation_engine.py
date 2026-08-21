"""Investigation Recommendation Engine.

Suggests first-line investigations mapped to the differentials and risk level,
separating what is already done (to review) from what to order. Cached: the
same structured inputs yield the same plan, so repeat runs are free.
"""
import json
from typing import Optional

from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import DifferentialDiagnosis, InvestigationPlan, MedicalRecord, RiskAssessment
from app.ai.providers.base import CostLedger
from app.ai.session.memory import ConversationMemory


class InvestigationEngineService(BaseAIService[InvestigationPlan]):
    stage = "investigation_engine"
    tier = "fast"
    temperature = 0.1
    max_tokens = 900
    output_model = InvestigationPlan

    async def recommend(
        self,
        memory: ConversationMemory,
        record: MedicalRecord,
        risk: RiskAssessment,
        differentials: DifferentialDiagnosis,
        *,
        ledger: Optional[CostLedger] = None,
    ) -> InvestigationPlan:
        system = (
            "You recommend pre-consultation investigations for a specialist at Satya Hospital "
            f"({memory.department.value}). Suggest only investigations a district Indian "
            "hospital can realistically perform (X-ray, USG, standard labs, ECG; MRI/CT only "
            "when clearly indicated). Map each test to the differentials/risk it serves in "
            "`rationale`. Respect cost: no shotgun panels. Anything the patient reports "
            "already having done goes in `already_done_to_review`, not re-ordered. Priorities: "
            "immediate = before the doctor sees them; urgent = same day; routine = can wait."
        )
        user = (
            f"Medical record:\n{record.model_dump_json()}\n"
            f"Risk:\n{risk.model_dump_json()}\n"
            f"Differentials:\n{differentials.model_dump_json()}"
        )
        return await self.run_json(
            system=system,
            user=user,
            ledger=ledger or memory.ledger,
            tag=str(memory.consultation_id),
            cache_ttl_s=3600,
        )
