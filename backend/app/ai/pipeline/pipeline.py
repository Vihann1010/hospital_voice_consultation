"""ClinicalPipeline — wires the stages in their canonical order.

    Conversation AI (live, in orchestrator)
        └─ per patient turn: Symptom Extractor  ──► memory slots/coverage
        └─ every N turns:    Medical JSON Generator ──► interim record
    On finalization:
        Medical JSON ─► Risk Detection ─► Clinical Summarizer
            ─► Differential Diagnosis ─► Investigation Engine
            ─► Patient Education  ─► ClinicalDossier (persisted)

Degradation policy: Medical JSON is the only critical stage; if any later
stage fails after its own retries, the dossier ships without it and the
failure is recorded in `pipeline_errors` — a doctor still gets the record.
"""
from typing import Optional

from app.ai.emergency import screen_utterance
from app.ai.pipeline.base_service import StageError
from app.ai.pipeline.clinical_summarizer import ClinicalSummarizerService
from app.ai.pipeline.differential_diagnosis import DifferentialDiagnosisService
from app.ai.pipeline.investigation_engine import InvestigationEngineService
from app.ai.pipeline.medical_json_generator import MedicalJSONGeneratorService
from app.ai.pipeline.patient_education import PatientEducationService
from app.ai.pipeline.risk_detection import RiskDetectionService
from app.ai.pipeline.schemas import (
    ClinicalDossier,
    MedicalRecord,
    PatientEducation,
    SymptomExtraction,
)
from app.ai.pipeline.symptom_extractor import SymptomExtractorService
from app.ai.providers.factory import LLMGateway, get_gateway
from app.ai.session.memory import ConversationMemory
from app.core.logging import get_logger
from app.models.enums import Department

logger = get_logger(__name__)


def fallback_patient_education(department: Department) -> PatientEducation:
    """Return safe two-line Hindi guidance when the education model is unavailable."""
    if department == Department.ORTHOPEDICS:
        instructions = [
            "दर्द वाले अंग को आराम दें और उसे अनावश्यक दबाव या चोट से बचाएं।",
            "अपनी सभी जांच रिपोर्ट साथ लाएं और डॉक्टर की सलाह के बिना दवा शुरू या बंद न करें।",
        ]
    else:
        instructions = [
            "आराम करें, पर्याप्त पानी पिएं और अपनी जांच रिपोर्ट तथा दवाओं की सूची साथ लाएं।",
            "तेज दर्द, अधिक रक्तस्राव, चक्कर या सांस लेने में परेशानी हो तो तुरंत अस्पताल जाएं।",
        ]
    return PatientEducation(language="hi", general_self_care=instructions)


class ClinicalPipeline:
    def __init__(self, gateway: Optional[LLMGateway] = None) -> None:
        gw = gateway or get_gateway()
        self.symptom_extractor = SymptomExtractorService(gw)
        self.medical_json = MedicalJSONGeneratorService(gw)
        self.risk = RiskDetectionService(gw)
        self.summarizer = ClinicalSummarizerService(gw)
        self.differential = DifferentialDiagnosisService(gw)
        self.investigations = InvestigationEngineService(gw)
        self.education = PatientEducationService(gw)

    # ------------------------------------------------------------- per turn
    def screen_deterministic(self, memory: ConversationMemory, utterance: str) -> bool:
        """Instant layer-1 emergency screen; returns True on a new emergency."""
        result = screen_utterance(utterance, memory.department)
        if result.is_emergency:
            memory.add_flags(result.flags, source="deterministic")
            was_emergency = memory.emergency
            memory.emergency = True
            return not was_emergency
        return False

    async def ingest_patient_turn(self, memory: ConversationMemory, utterance: str) -> None:
        """Symptom extraction + memory merge for one turn (fast tier)."""
        try:
            extraction: SymptomExtraction = await self.symptom_extractor.extract_turn(
                memory, utterance
            )
        except StageError:
            logger.exception(
                "symptom_extraction_failed",
                extra={"consultation_id": str(memory.consultation_id)},
            )
            return
        async with memory.lock:
            memory.update_slots(extraction.slots)
            for symptom in extraction.symptoms:
                memory.symptoms.append(symptom.model_dump())
            if extraction.possible_red_flags:
                memory.add_flags(extraction.possible_red_flags, source="llm")
            if extraction.language_detected:
                memory.language = extraction.language_detected

    async def refresh_medical_record(self, memory: ConversationMemory) -> Optional[MedicalRecord]:
        """Mid-session record regeneration (cost-gated by the caller's cadence)."""
        try:
            record = await self.medical_json.generate(memory)
        except StageError:
            logger.exception(
                "interim_medical_json_failed",
                extra={"consultation_id": str(memory.consultation_id)},
            )
            return None
        async with memory.lock:
            memory.medical_json = record.model_dump()
        return record

    # ---------------------------------------------------------- finalization
    async def finalize(self, memory: ConversationMemory) -> ClinicalDossier:
        dossier = ClinicalDossier()
        cid = str(memory.consultation_id)

        # 1. Medical JSON — critical; fall back to last interim record.
        try:
            record = await self.medical_json.generate(memory)
        except StageError as exc:
            logger.exception("final_medical_json_failed", extra={"consultation_id": cid})
            dossier.pipeline_errors.append(str(exc))
            record = (
                MedicalRecord.model_validate(memory.medical_json)
                if memory.medical_json
                else MedicalRecord(red_flags=memory.all_flags)
            )
        dossier.medical_json = record

        # 2. Risk detection.
        try:
            dossier.risk_assessment = await self.risk.assess(memory, record)
        except StageError as exc:
            dossier.pipeline_errors.append(str(exc))
            dossier.risk_assessment.emergency = memory.emergency
            if memory.emergency:
                dossier.risk_assessment.overall_risk = "high"
                dossier.risk_assessment.triage_priority = "urgent"

        # 3. Clinical summary.
        try:
            dossier.clinical_summary = await self.summarizer.summarize(
                memory, record, dossier.risk_assessment
            )
        except StageError as exc:
            dossier.pipeline_errors.append(str(exc))

        # 4. Differential diagnosis.
        try:
            dossier.differential_diagnosis = await self.differential.generate(
                memory, record, dossier.risk_assessment, dossier.clinical_summary
            )
        except StageError as exc:
            dossier.pipeline_errors.append(str(exc))

        # 5. Investigations.
        try:
            dossier.investigations = await self.investigations.recommend(
                memory, record, dossier.risk_assessment, dossier.differential_diagnosis
            )
        except StageError as exc:
            dossier.pipeline_errors.append(str(exc))

        # 6. Patient education.
        try:
            dossier.patient_education = await self.education.generate(
                memory, record, dossier.risk_assessment
            )
        except StageError as exc:
            dossier.pipeline_errors.append(str(exc))
            dossier.patient_education = fallback_patient_education(memory.department)

        dossier.conversation_meta = memory.meta()
        logger.info(
            "pipeline_finalized",
            extra={
                "consultation_id": cid,
                "risk": dossier.risk_assessment.overall_risk,
                "emergency": dossier.risk_assessment.emergency,
                "errors": len(dossier.pipeline_errors),
                "usage": memory.ledger.snapshot(),
            },
        )
        return dossier


clinical_pipeline = ClinicalPipeline()
