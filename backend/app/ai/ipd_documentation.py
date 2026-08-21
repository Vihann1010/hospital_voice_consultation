"""AI assistance for the ward.

Two things a model is genuinely good at, and one it must never be trusted
with.

**Good:** turning a week of scattered notes, observations and drug charts into
a discharge summary a junior doctor would otherwise spend forty minutes
writing, and into a handover a night nurse can read in ninety seconds. Both
are summarisation of material already in the record.

**Never:** deciding whether a patient is deteriorating. That is NEWS2, in
`app/ipd/early_warning.py`, and it is arithmetic — it runs with the network
down, the API key expired, and the vendor having an outage. A model may
describe the trend it sees; it does not raise or lower the alarm.

Everything generated here is written to the record flagged `ai_generated`,
unsigned, and requires a clinician to review it. A discharge summary is a
legal document and goes out under a doctor's name, so the doctor reads it.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.ai.pipeline.base_service import BaseAIService, StageError
from app.core.logging import get_logger


class DischargeMedicine(BaseModel):
    name: str = ""
    dose: str = ""
    route: str = ""
    frequency: str = ""
    duration: str = ""
    instructions: Optional[str] = None


class DischargeSummaryDraft(BaseModel):
    """The structure the model must return.

    Every field defaults to empty rather than being required: a stay with no
    procedures should produce an empty list, not a validation failure that
    loses the whole summary.
    """

    presenting_complaint: str = ""
    history_summary: str = ""
    hospital_course: str = ""
    significant_findings: str = ""
    procedures_performed: List[str] = Field(default_factory=list)
    condition_at_discharge: str = ""
    discharge_medications: List[DischargeMedicine] = Field(default_factory=list)
    diet_and_activity: str = ""
    follow_up_instructions: str = ""
    warning_signs: List[str] = Field(default_factory=list)
    # What the model could not determine from the record. Surfaced to the
    # doctor rather than silently guessed.
    uncertain_or_missing: List[str] = Field(default_factory=list)


class HandoverDraft(BaseModel):
    one_line: str = ""
    overnight_events: str = ""
    current_concerns: List[str] = Field(default_factory=list)
    watch_for: List[str] = Field(default_factory=list)
    pending_tasks: List[str] = Field(default_factory=list)

logger = get_logger(__name__)


DISCHARGE_SYSTEM = """You are a clinical documentation assistant at Satya Hospital, \
drafting a discharge summary from an inpatient record for a doctor to review and sign.

Absolute rules:
- Use ONLY what appears in the record given to you. If something is not recorded, \
omit it. Never infer a diagnosis, a drug, a dose, or a finding that is not written down.
- Where the record is genuinely unclear, say so plainly in the relevant field rather \
than resolving it yourself.
- Write the way a doctor writes for another doctor: precise, compact, standard \
abbreviations, no filler and no reassurance.
- Medicines on discharge must be copied exactly as recorded — name, dose, route, \
frequency, duration. Do not tidy, convert, or "correct" a dose.

Respond with ONLY a JSON object, no prose and no markdown fences:
{
  "presenting_complaint": string,
  "history_summary": string,
  "hospital_course": string,
  "significant_findings": string,
  "procedures_performed": [string],
  "condition_at_discharge": string,
  "discharge_medications": [
    {"name": string, "dose": string, "route": string, "frequency": string,
     "duration": string, "instructions": string|null}
  ],
  "diet_and_activity": string,
  "follow_up_instructions": string,
  "warning_signs": [string],
  "uncertain_or_missing": [string]
}

"hospital_course" is the heart of it: what happened, in order, in three to six \
sentences. "warning_signs" are the specific things that should bring the patient \
back urgently, in plain language a family member can act on."""


HANDOVER_SYSTEM = """You are preparing a nursing shift handover at Satya Hospital.

Use only the record provided. The incoming nurse has ninety seconds and needs to \
know what changed and what to watch, not the full history.

Respond with ONLY a JSON object:
{
  "one_line": string,
  "overnight_events": string,
  "current_concerns": [string],
  "watch_for": [string],
  "pending_tasks": [string]
}

"one_line" is age, sex, admitting problem and day of stay in a single sentence. \
Note any trend in the observations factually — a rising score, a falling blood \
pressure — without judging whether to escalate; that decision belongs to the \
early warning score and the nurse in charge."""


def build_stay_record(
    *,
    patient: Dict[str, Any],
    admission: Dict[str, Any],
    occupancies: List[Dict[str, Any]],
    vitals: List[Dict[str, Any]],
    notes: List[Dict[str, Any]],
    medications: List[Dict[str, Any]],
    investigations: Optional[List[Dict[str, Any]]] = None,
    max_vitals: int = 30,
) -> str:
    """Assemble the stay into the text a model is asked to summarise.

    Observations are thinned to the most recent and the most abnormal rather
    than all of them: a week in a bed is several hundred rows, and burying the
    two that mattered inside three hundred normal ones makes the summary
    worse, not better.
    """
    lines: List[str] = []

    lines.append("PATIENT")
    lines.append(
        f"  {patient.get('name')} — {patient.get('age')} yrs, "
        f"{patient.get('gender')}, UHID {patient.get('uhid')}"
    )
    allergies = admission.get("allergies") or []
    lines.append(f"  Allergies: {', '.join(allergies) if allergies else 'none recorded'}")

    lines.append("\nADMISSION")
    lines.append(f"  IP number: {admission.get('ip_number')}")
    lines.append(f"  Admitted: {admission.get('admitted_at')}")
    if admission.get("discharged_at"):
        lines.append(f"  Discharged: {admission.get('discharged_at')}")
    lines.append(f"  Under: {admission.get('admitting_doctor_name')}")
    lines.append(f"  Reason: {admission.get('reason_for_admission') or 'not recorded'}")
    lines.append(
        f"  Provisional diagnosis: {admission.get('provisional_diagnosis') or 'not recorded'}"
    )
    if admission.get("final_diagnosis"):
        lines.append(f"  Final diagnosis: {admission.get('final_diagnosis')}")

    if occupancies:
        lines.append("\nWARD MOVEMENTS")
        for item in occupancies:
            end = item.get("ended_at") or "current"
            lines.append(
                f"  {item.get('ward_name')} bed {item.get('bed_label')}: "
                f"{item.get('started_at')} to {end}"
            )

    if vitals:
        # Most recent, plus anything that scored badly, without duplication.
        recent = vitals[-max_vitals:]
        abnormal = [v for v in vitals if (v.get("news2_score") or 0) >= 5]
        seen = set()
        chosen = []
        for item in abnormal + recent:
            key = item.get("recorded_at")
            if key not in seen:
                seen.add(key)
                chosen.append(item)
        chosen.sort(key=lambda v: v.get("recorded_at") or "")

        lines.append(f"\nOBSERVATIONS ({len(vitals)} recorded, {len(chosen)} shown)")
        for item in chosen:
            parts = [str(item.get("recorded_at"))]
            for label, key, unit in (
                ("RR", "respiratory_rate", "/min"),
                ("SpO2", "spo2_percent", "%"),
                ("BP", "systolic_bp", " mmHg"),
                ("HR", "pulse", "/min"),
                ("T", "temperature_c", "C"),
            ):
                value = item.get(key)
                if value is not None:
                    parts.append(f"{label} {value}{unit}")
            if item.get("news2_score") is not None:
                parts.append(f"NEWS2 {item['news2_score']} ({item.get('news2_risk')})")
            lines.append("  " + ", ".join(parts))

    if medications:
        lines.append("\nMEDICATIONS DURING STAY")
        for item in medications:
            state = item.get("status")
            lines.append(
                f"  {item.get('drug_name')} {item.get('strength') or ''} "
                f"{item.get('dose')} {item.get('route')} {item.get('frequency_code')} "
                f"[{state}] {item.get('instructions') or ''}".strip()
            )

    if investigations:
        lines.append("\nINVESTIGATIONS")
        for item in investigations:
            lines.append(f"  {item.get('name')}: {item.get('result') or 'reported'}")

    if notes:
        lines.append("\nCLINICAL NOTES")
        for item in notes:
            lines.append(
                f"  [{item.get('created_at')}] {item.get('note_type')} — "
                f"{item.get('author_name')}"
            )
            content = (item.get("content") or "").strip()
            if content:
                lines.append(f"    {content}")

    return "\n".join(lines)


class DischargeSummaryService(BaseAIService[DischargeSummaryDraft]):
    """Drafts a discharge summary. The doctor signs it, or does not."""

    stage = "discharge_summary"
    output_model = DischargeSummaryDraft
    # A discharge summary is the one document from this stay that follows the
    # patient out of the building, so it uses the better model and is given
    # room to be complete.
    tier = "dialogue"
    temperature = 0.2
    max_tokens = 2000

    async def draft(self, stay_record: str, *, tag: str = "-") -> DischargeSummaryDraft:
        return await self.run_json(
            system=DISCHARGE_SYSTEM,
            user=f"Inpatient record:\n\n{stay_record}\n\nProduce the JSON now.",
            tag=tag,
        )


class HandoverService(BaseAIService[HandoverDraft]):
    """Nursing shift handover — short, frequent, and cheap by design."""

    stage = "nursing_handover"
    output_model = HandoverDraft
    tier = "fast"
    temperature = 0.2
    max_tokens = 700

    async def draft(self, stay_record: str, *, tag: str = "-") -> HandoverDraft:
        return await self.run_json(
            system=HANDOVER_SYSTEM,
            user=f"Inpatient record:\n\n{stay_record}\n\nProduce the JSON now.",
            tag=tag,
        )


def render_discharge_summary(draft: DischargeSummaryDraft) -> str:
    """Turn the structured draft into the text placed in the record.

    Rendered here rather than by the model so the document's shape is fixed
    and predictable, and a missing field is visibly missing rather than
    quietly dropped.
    """
    payload = draft.model_dump()

    def section(title: str, body: Any) -> List[str]:
        if not body:
            return []
        out = [title.upper()]
        if isinstance(body, list):
            out += [f"  - {item}" for item in body if item]
        else:
            out.append(f"  {body}")
        out.append("")
        return out

    lines: List[str] = []
    lines += section("Presenting complaint", payload.get("presenting_complaint"))
    lines += section("History", payload.get("history_summary"))
    lines += section("Hospital course", payload.get("hospital_course"))
    lines += section("Significant findings", payload.get("significant_findings"))
    lines += section("Procedures performed", payload.get("procedures_performed"))
    lines += section("Condition at discharge", payload.get("condition_at_discharge"))

    medicines = payload.get("discharge_medications") or []
    if medicines:
        lines.append("MEDICINES ON DISCHARGE")
        for index, medicine in enumerate(medicines, start=1):
            parts = [
                medicine.get("name", ""),
                medicine.get("dose", ""),
                medicine.get("route", ""),
                medicine.get("frequency", ""),
            ]
            line = f"  {index}. " + " · ".join(part for part in parts if part)
            if medicine.get("duration"):
                line += f" — {medicine['duration']}"
            lines.append(line)
            if medicine.get("instructions"):
                lines.append(f"     {medicine['instructions']}")
        lines.append("")

    lines += section("Diet and activity", payload.get("diet_and_activity"))
    lines += section("Follow-up", payload.get("follow_up_instructions"))
    lines += section("Return immediately if", payload.get("warning_signs"))

    uncertain = payload.get("uncertain_or_missing") or []
    if uncertain:
        lines.append("NOT CLEAR FROM THE RECORD — please confirm before signing")
        lines += [f"  - {item}" for item in uncertain]
        lines.append("")

    return "\n".join(lines).strip()
