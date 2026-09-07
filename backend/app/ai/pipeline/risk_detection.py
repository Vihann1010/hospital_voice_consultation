"""Risk Detection — layer 2 of red-flag detection.

Layer 1 (app/ai/emergency.py) is deterministic pattern screening on every
utterance. This service reasons over the *structured* MedicalRecord to grade
overall risk, surface red flags the patterns cannot catch (combinations, age
context, department nuances), and set triage priority for the front desk.
"""
import json
from typing import Optional

from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import MedicalRecord, RiskAssessment
from app.ai.providers.base import CostLedger
from app.ai.session.memory import ConversationMemory

_DEPT_RED_FLAG_GUIDE = {
    "orthopedics": (
        "Orthopedic red flags include: suspected open/deformed fracture, neurovascular "
        "compromise (numb/cold/pulseless limb), cauda equina features (saddle anaesthesia, "
        "urinary retention/incontinence with back pain), septic arthritis features (hot "
        "swollen joint + fever), night pain with weight loss or cancer history, significant "
        "trauma in the elderly, progressive neurological deficit."
    ),
    "gynecology": (
        "Gynecological red flags include: pregnancy with bleeding or severe abdominal pain "
        "(possible ectopic/miscarriage), reduced fetal movements, heavy bleeding with "
        "dizziness/syncope, postmenopausal bleeding, fever with pelvic pain and discharge "
        "(possible PID/sepsis), severe hyperemesis with dehydration."
    ),
}


class RiskDetectionService(BaseAIService[RiskAssessment]):
    stage = "risk_detection"
    tier = "fast"
    temperature = 0.0
    max_tokens = 800
    output_model = RiskAssessment

    async def assess(
        self,
        memory: ConversationMemory,
        record: MedicalRecord,
        *,
        ledger: Optional[CostLedger] = None,
    ) -> RiskAssessment:
        guide = _DEPT_RED_FLAG_GUIDE.get(memory.department.value, "")
        system = (
            "You are a triage risk-assessment model for Satya Hospital's "
            f"{memory.department.value} department. Grade risk conservatively but honestly — "
            "do not inflate routine complaints, do not miss dangerous combinations. "
            f"{guide} Deterministic screening already flagged: "
            f"{memory.deterministic_flags or 'none'} — evaluate each of these too. "
            "emergency=true only for conditions needing same-day emergency care. "
            "recommended_action is one sentence for hospital staff, not the patient."
        )
        user = (
            f"Patient: {json.dumps(memory.patient_info, ensure_ascii=False)}\n"
            f"Structured medical record:\n{record.model_dump_json()}"
        )
        assessment = await self.run_json(
            system=system, user=user, ledger=ledger or memory.ledger, tag=str(memory.consultation_id)
        )
        # Deterministic hits can raise but never lower the machine assessment.
        if memory.deterministic_flags and not assessment.emergency:
            assessment.emergency = memory.emergency or assessment.emergency
        if memory.emergency:
            assessment.emergency = True
            if assessment.overall_risk in {"low", "moderate"}:
                assessment.overall_risk = "high"
            if assessment.triage_priority in {"routine", "soon"}:
                assessment.triage_priority = "urgent"
        return assessment
