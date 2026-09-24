"""Structured output contracts for every pipeline stage.

Nothing between services is free text: each stage produces one of these
validated models, and downstream stages consume `.model_dump()` of upstream
stages. Fields are optional/defaulted so partially-informative model output
still validates instead of failing the visit.
"""
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StageModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------- turn
class ConversationTurnPlan(StageModel):
    """Structured output of the Conversation AI for one spoken turn."""

    utterance: str = ""
    language: Literal["en", "hi", "mixed"] = "en"
    phase: Literal["greeting", "exploring", "clarifying", "wrapping_up", "emergency"] = "exploring"
    topics_addressed: List[str] = Field(default_factory=list)
    conversation_complete: bool = False
    handoff_note: Optional[str] = None


# ---------------------------------------------------------------- extraction
class ExtractedSymptom(StageModel):
    name: str
    details: Optional[str] = None
    severity: Optional[Literal["mild", "moderate", "severe"]] = None
    onset: Optional[str] = None
    negated: bool = False  # patient explicitly denied it


class SymptomExtraction(StageModel):
    symptoms: List[ExtractedSymptom] = Field(default_factory=list)
    slots: Dict[str, Optional[str]] = Field(default_factory=dict)
    possible_red_flags: List[str] = Field(default_factory=list)
    language_detected: Optional[Literal["en", "hi", "mixed"]] = None


# -------------------------------------------------------------- medical json
class PainDetail(StageModel):
    location: Optional[str] = None
    character: Optional[str] = None
    score_out_of_10: Optional[float] = None
    aggravating_factors: Optional[str] = None
    relieving_factors: Optional[str] = None


class MedicineItem(StageModel):
    name: str
    dose_or_frequency: Optional[str] = None


class SurgeryItem(StageModel):
    name: str
    year_or_when: Optional[str] = None


class SymptomItem(StageModel):
    name: str
    details: Optional[str] = None


class MedicalRecord(StageModel):
    chief_complaint: Optional[str] = None
    symptoms: List[SymptomItem] = Field(default_factory=list)
    pain: PainDetail = Field(default_factory=PainDetail)
    duration: Optional[str] = None
    medical_history: List[str] = Field(default_factory=list)
    current_medicines: List[MedicineItem] = Field(default_factory=list)
    previous_surgeries: List[SurgeryItem] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    department_specific: Dict[str, Any] = Field(default_factory=dict)
    red_flags: List[str] = Field(default_factory=list)
    summary_for_doctor: Optional[str] = None


# --------------------------------------------------------------------- risk
class RedFlagFinding(StageModel):
    flag: str
    rationale: Optional[str] = None
    severity: Literal["low", "moderate", "high", "critical"] = "moderate"


class RiskAssessment(StageModel):
    overall_risk: Literal["low", "moderate", "high", "critical"] = "low"
    emergency: bool = False
    red_flags: List[RedFlagFinding] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    triage_priority: Literal["routine", "soon", "urgent", "immediate"] = "routine"


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")


def devanagari_lines(lines: List[str]) -> List[str]:
    """Refuse Hindi written in Roman letters.

    Asked for Hindi, a model mirrors the patient: an intake spoken in Hinglish
    comes back as "daant mein tez dard", which is not what a patient reading
    their printed copy needs, and not what the section says it is. A line is
    accepted when it is mostly Devanagari — a drug name or a number in Latin
    letters is normal and stays. Rejecting here is what triggers the stage's
    repair round, with this sentence handed back to the model.
    """
    for line in lines:
        text = (line or "").strip()
        if not text:
            continue
        devanagari = len(_DEVANAGARI.findall(text))
        latin = len(_LATIN.findall(text))
        if devanagari == 0 or latin > devanagari:
            raise ValueError(
                "must be written in the Devanagari script, not Roman transliteration "
                "(दांत में दर्द, not 'daant mein dard'); "
                f"this line is not: {text[:60]!r}"
            )
    return lines


# ------------------------------------------------------------------ summary
class ClinicalSummary(StageModel):
    one_liner: Optional[str] = None
    history_of_present_illness: Optional[str] = None
    #: The same history as short bullets, and each bullet again in Hindi.
    #: Produced in the summariser's own call, not a second one: the doctor
    #: reads the English, the patient reads the Hindi on the printed copy.
    history_points: List[str] = Field(default_factory=list)
    history_points_hi: List[str] = Field(default_factory=list)

    _hindi = field_validator("history_points_hi")(devanagari_lines)

    pertinent_positives: List[str] = Field(default_factory=list)
    pertinent_negatives: List[str] = Field(default_factory=list)
    relevant_background: List[str] = Field(default_factory=list)
    summary_for_doctor: Optional[str] = None


# ------------------------------------------------------------- differential
class DifferentialItem(StageModel):
    condition: str
    likelihood: Literal["high", "moderate", "low"] = "moderate"
    supporting_features: List[str] = Field(default_factory=list)
    features_against: List[str] = Field(default_factory=list)
    would_change_with: Optional[str] = None  # info/test that would confirm or exclude


class DifferentialDiagnosis(StageModel):
    differentials: List[DifferentialItem] = Field(default_factory=list)
    reasoning_note: Optional[str] = None
    disclaimer: str = (
        "Decision-support for the treating doctor only; not a diagnosis and "
        "not a substitute for clinical examination."
    )


# ------------------------------------------------------------ investigations
class InvestigationItem(StageModel):
    test: str
    priority: Literal["immediate", "urgent", "routine"] = "routine"
    rationale: Optional[str] = None
    fasting_or_prep_required: Optional[str] = None


class InvestigationPlan(StageModel):
    investigations: List[InvestigationItem] = Field(default_factory=list)
    already_done_to_review: List[str] = Field(default_factory=list)
    note_for_doctor: Optional[str] = None


# ---------------------------------------------------------------- education
class PatientEducation(StageModel):
    language: Literal["en", "hi", "mixed"] = "en"
    understanding_your_visit: Optional[str] = None
    what_to_expect_at_hospital: Optional[str] = None
    general_self_care: List[str] = Field(default_factory=list)
    warning_signs_return_immediately: List[str] = Field(default_factory=list)
    #: The same advice again, wholly in Hindi, so the patient's copy can be
    #: printed in one language rather than a mixture. Written in the same call.
    general_self_care_hi: List[str] = Field(default_factory=list)
    warning_signs_return_immediately_hi: List[str] = Field(default_factory=list)

    _hindi = field_validator(
        "general_self_care_hi", "warning_signs_return_immediately_hi"
    )(devanagari_lines)
    questions_to_ask_your_doctor: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "General information only — your doctor's advice after examining you "
        "always takes precedence."
    )


# ------------------------------------------------------------------ dossier
class ClinicalDossier(StageModel):
    """The complete artifact persisted to consultations.medical_json."""

    schema_version: str = "2.0"
    medical_json: MedicalRecord = Field(default_factory=MedicalRecord)
    risk_assessment: RiskAssessment = Field(default_factory=RiskAssessment)
    clinical_summary: ClinicalSummary = Field(default_factory=ClinicalSummary)
    differential_diagnosis: DifferentialDiagnosis = Field(default_factory=DifferentialDiagnosis)
    investigations: InvestigationPlan = Field(default_factory=InvestigationPlan)
    patient_education: PatientEducation = Field(default_factory=PatientEducation)
    conversation_meta: Dict[str, Any] = Field(default_factory=dict)
    pipeline_errors: List[str] = Field(default_factory=list)


# ------------------------------------------------------------------ copilot
class MedicationAlert(StageModel):
    kind: Literal["interaction", "allergy", "duplicate"]
    severity: Literal["info", "caution", "serious"] = "caution"
    medicines_involved: List[str] = Field(default_factory=list)
    description: str
    suggested_action: Optional[str] = None
    # Provenance is surfaced in the UI: rules are deterministic, ai is inferred.
    detected_by: Literal["rule", "ai"] = "ai"


class FollowUpQuestion(StageModel):
    question: str
    why_it_matters: Optional[str] = None
    targets: Optional[str] = None  # differential or red flag it discriminates


class ReferralSuggestion(StageModel):
    specialty: str
    urgency: Literal["routine", "soon", "urgent"] = "routine"
    reason: str


class CopilotAIOutput(StageModel):
    """Single LLM call covering the inferential half of the briefing."""

    interaction_alerts: List[MedicationAlert] = Field(default_factory=list)
    follow_up_questions: List[FollowUpQuestion] = Field(default_factory=list)
    referrals: List[ReferralSuggestion] = Field(default_factory=list)
    notes: Optional[str] = None


class CopilotBriefing(StageModel):
    schema_version: str = "1.0"
    generated_at: Optional[str] = None
    medication_alerts: List[MedicationAlert] = Field(default_factory=list)
    follow_up_questions: List[FollowUpQuestion] = Field(default_factory=list)
    referrals: List[ReferralSuggestion] = Field(default_factory=list)
    notes: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "AI-generated decision support. Every item must be verified by the "
        "treating doctor, who remains the final authority on this patient's care."
    )


# ------------------------------------------------------------ lab reports
class ReportFinding(StageModel):
    finding: str
    significance: Optional[str] = None
    severity: Literal["incidental", "notable", "significant", "urgent"] = "notable"


class ReportSummary(StageModel):
    """Narrative layer over the deterministic analysis of one report.

    The abnormal values themselves are computed arithmetically before this
    stage runs; the model explains them, it does not decide them.
    """

    report_type: Optional[str] = None
    headline: Optional[str] = None
    doctor_summary: Optional[str] = None
    key_findings: List[ReportFinding] = Field(default_factory=list)
    patterns_noticed: List[str] = Field(default_factory=list)
    comparison_with_previous: Optional[str] = None
    suggested_next_steps: List[str] = Field(default_factory=list)
    limitations: Optional[str] = None
    disclaimer: str = (
        "AI-generated interpretation of an uploaded report. Values were compared "
        "arithmetically against reference ranges; the narrative is advisory and the "
        "treating doctor remains the final authority."
    )
