"""Clinical Summarizer — the doctor's 30-second read.

Consumes the structured MedicalRecord + RiskAssessment (never raw text alone)
and produces the HPI-style summary shown at the top of the doctor's view.
"""
import json
from typing import Optional

from app.core.config import settings
from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import ClinicalSummary, MedicalRecord, RiskAssessment
from app.ai.providers.base import CostLedger
from app.ai.session.memory import ConversationMemory
from app.departments import label_for


class ClinicalSummarizerService(BaseAIService[ClinicalSummary]):
    stage = "clinical_summarizer"
    tier = "dialogue"  # quality matters most here; worth the stronger model
    temperature = 0.2
    max_tokens = 900
    output_model = ClinicalSummary

    async def summarize(
        self,
        memory: ConversationMemory,
        record: MedicalRecord,
        risk: RiskAssessment,
        *,
        ledger: Optional[CostLedger] = None,
    ) -> ClinicalSummary:
        # Named from the consultant register, never from a hardcoded pair —
        # the old version handed every non-orthopedic patient to the
        # gynaecologist, whatever department they had actually come to.
        label = label_for(memory.department)
        doctor = f"{memory.doctor_name} ({label})" if memory.doctor_name else f"the {label} consultant"
        system = (
            f"You write pre-consultation clinical summaries for {doctor} at {settings.brand_for(memory.department)}. "
            "Audience: the treating doctor, seconds before walking in. Style: precise clinical "
            "prose, standard abbreviations fine, no hedging filler, no invented findings. "
            "one_liner: age/gender + chief complaint + duration in one sentence. "
            "history_of_present_illness: 3-6 sentences in chronological order. "
            "history_points: the same history as 3-6 short bullets, one fact each, "
            "in chronological order. "
            "history_points_hi: exactly those bullets in Hindi, in Devanagari, in the "
            "same order and the same number, worded as a patient would understand them. "
            "Translate only what the English bullet says; add nothing. "
            "pertinent_negatives: only genuinely informative denials. "
            "summary_for_doctor: the single paragraph you'd say aloud handing over the patient."
        )
        user = (
            f"Patient: {json.dumps(memory.patient_info, ensure_ascii=False)}\n"
            f"Medical record:\n{record.model_dump_json()}\n"
            f"Risk assessment:\n{risk.model_dump_json()}"
        )
        return await self.run_json(
            system=system, user=user, ledger=ledger or memory.ledger, tag=str(memory.consultation_id)
        )
