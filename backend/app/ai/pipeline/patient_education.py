"""Patient Education Generator.

Plain-language, non-diagnostic guidance in the patient's own language: what
to expect at the hospital, safe general self-care, and the warning signs that
mean 'come back immediately'. Cached — common presentations reuse output.
"""
import json
from typing import Optional

from app.core.config import settings
from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import MedicalRecord, PatientEducation, RiskAssessment
from app.ai.providers.base import CostLedger
from app.ai.session.memory import ConversationMemory


class PatientEducationService(BaseAIService[PatientEducation]):
    stage = "patient_education"
    tier = "fast"
    temperature = 0.3
    max_tokens = 1000
    output_model = PatientEducation

    async def generate(
        self,
        memory: ConversationMemory,
        record: MedicalRecord,
        risk: RiskAssessment,
        *,
        ledger: Optional[CostLedger] = None,
    ) -> PatientEducation:
        system = (
            f"You write patient education for {settings.brand_for(memory.department)}. Audience: the patient and their "
            f"family; write in language '{memory.language}' (hi = simple Hindi in Devanagari, "
            "mixed = natural Hinglish, en = simple Indian English at an 8th-grade level). "
            "STRICT rules: do NOT name a diagnosis or imply one; do NOT recommend medicines, "
            "doses, or prescription changes; self-care is only universally safe measures "
            "(rest, hydration, warm/cold compress where clearly appropriate, keeping reports "
            "handy). warning_signs_return_immediately must reflect this department and this "
            "presentation. Tone: warm, calm, respectful — never alarming. "
            "Write general_self_care and warning_signs_return_immediately in simple Indian "
            "English, and general_self_care_hi and warning_signs_return_immediately_hi as the "
            "same advice wholly in Hindi, in Devanagari, line for line and in the same order. "
            "The Hindi must contain no English words beyond a drug or test name that has no "
            "Hindi equivalent: the patient's copy is printed in one language. Write it in "
            "the Devanagari script even when the patient spoke Hinglish: "
            "गर्म पानी पिएं — never 'garm paani piyen'."
        )
        user = (
            f"Department: {memory.department.value}\n"
            f"Presentation (context only, do not echo clinical terms):\n{record.model_dump_json()}\n"
            f"Risk level: {risk.overall_risk}; emergency: {risk.emergency}"
        )
        return await self.run_json(
            system=system,
            user=user,
            ledger=ledger or memory.ledger,
            tag=str(memory.consultation_id),
            cache_ttl_s=3600,
        )
