"""Symptom Extractor — runs on the fast tier after every patient turn.

Reads the latest patient utterance in context and emits structured slot
updates + symptoms, which the memory merges into the collection checklist.
This is what makes coverage tracking (and therefore completeness detection)
work without ever re-reading the whole transcript.
"""
from typing import Optional

from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import SymptomExtraction
from app.ai.providers.base import CostLedger
from app.ai.session.memory import ConversationMemory, slot_keys_for


class SymptomExtractorService(BaseAIService[SymptomExtraction]):
    stage = "symptom_extractor"
    tier = "fast"
    temperature = 0.0
    max_tokens = 700
    output_model = SymptomExtraction

    async def extract_turn(
        self, memory: ConversationMemory, patient_utterance: str, *, ledger: Optional[CostLedger] = None
    ) -> SymptomExtraction:
        keys = slot_keys_for(memory.department)
        system = (
            "You are a clinical information extraction model for a hospital intake call in "
            f"the {memory.department.value} department. Extract ONLY what the patient actually "
            "stated — never infer or invent. Use the patient's meaning, not their exact slang. "
            "For `slots`, only include keys whose information appears in THIS utterance (given "
            "the immediate context); allowed keys: "
            + ", ".join(keys)
            + ". Values are short English phrases. Mark `negated: true` for symptoms the "
            "patient explicitly denied. `possible_red_flags` lists any concerning feature "
            "worth a clinician's attention (short snake_case labels)."
        )
        recent = memory.chat_window()[-4:]
        context = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
        user = (
            f"Recent context:\n{context}\n\n"
            f"NEW PATIENT UTTERANCE to extract from:\n{patient_utterance}"
        )
        return await self.run_json(
            system=system, user=user, ledger=ledger or memory.ledger, tag=str(memory.consultation_id)
        )
