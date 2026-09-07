"""Copilot AI stage — the inferential half of the doctor's briefing.

Deterministic rules (medication_rules.py) handle duplicates and allergy
conflicts. This stage covers what rules cannot: pharmacodynamic interactions,
the questions worth asking next, and referral suggestions. One LLM call
produces all three to keep the doctor's panel fast and cheap.

Nothing here is authoritative. Every item is rendered in the UI under an
"AI Recommendation" label with the doctor's decision recorded separately.
"""
import json
from typing import Dict, List, Optional

from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import CopilotAIOutput
from app.ai.providers.base import CostLedger


class CopilotAIService(BaseAIService[CopilotAIOutput]):
    stage = "copilot"
    tier = "dialogue"  # clinical reasoning quality matters in the doctor's hands
    temperature = 0.2
    max_tokens = 1400
    output_model = CopilotAIOutput

    async def brief(
        self,
        *,
        department: str,
        patient: Dict,
        dossier: Dict,
        medicines: List[str],
        allergies: List[str],
        rule_alerts: List[Dict],
        ledger: Optional[CostLedger] = None,
        tag: str = "-",
    ) -> CopilotAIOutput:
        system = (
            "You are a clinical copilot assisting a specialist at Satya Hospital "
            f"({department}). You assist — you never decide. The doctor examines the "
            "patient and holds final authority.\n\n"
            "Produce three things:\n"
            "1. interaction_alerts — clinically meaningful drug-drug interactions among the "
            "patient's CURRENT medicines. kind must be \"interaction\". Report only "
            "interactions that would change management; do not restate the duplicate or "
            "allergy alerts already found by rules (listed below). Empty list is a fine "
            "answer. Severity: serious = avoid or requires monitoring; caution = be aware; "
            "info = minor.\n"
            "2. follow_up_questions — 3-6 questions the doctor should ask that the intake "
            "conversation did not cover, each one discriminating between the differentials "
            "or clarifying a red flag. Not generic questions; specific to this patient.\n"
            "3. referrals — only when another specialty genuinely needs to be involved; "
            "an empty list is expected for routine cases.\n\n"
            "Ground everything in the supplied record. Never invent history, and never "
            "state a diagnosis as established."
        )
        user = json.dumps(
            {
                "patient": patient,
                "current_medicines": medicines,
                "allergies": allergies,
                "alerts_already_found_by_rules": rule_alerts,
                "clinical_record": dossier.get("medical_json", {}),
                "risk_assessment": dossier.get("risk_assessment", {}),
                "clinical_summary": dossier.get("clinical_summary", {}),
                "differential_diagnosis": dossier.get("differential_diagnosis", {}),
                "investigations": dossier.get("investigations", {}),
            },
            ensure_ascii=False,
        )
        return await self.run_json(system=system, user=user, ledger=ledger, tag=tag)
