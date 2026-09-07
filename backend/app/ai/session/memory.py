"""Conversation memory for one consultation.

Holds the rolling dialogue, a department-aware slot checklist (what has been
collected vs what is still missing), extracted symptoms, red flags, and the
cost ledger. Completeness is decided here deterministically — the model's own
`conversation_complete` signal is honoured only once required coverage exists,
so the AI knows *exactly* when enough information has been collected and can
never wrap up early.
"""
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.ai.providers.base import CostLedger
from app.core.config import settings
from app.models.enums import Department

# ---------------------------------------------------------------------------
# Slot definitions (the collection checklist)
# ---------------------------------------------------------------------------


@dataclass
class SlotSpec:
    key: str
    label: str
    required: bool


# The intake is deliberately short. A patient waiting to be seen will answer a
# handful of questions well and a long questionnaire badly, and everything here
# is a starting point for the doctor rather than a substitute for the
# consultation. Only the starred items are required, which caps a normal
# interview at roughly five questions.
COMMON_SLOTS: List[SlotSpec] = [
    SlotSpec("chief_complaint", "Main problem bringing them in", True),
    SlotSpec("duration", "How long it has been going on", True),
    SlotSpec("pain_details", "Severity and what makes it better or worse", True),
    SlotSpec("medical_history", "Existing conditions and current medicines", True),
    SlotSpec("allergies", "Allergies to any medicine", True),
    # Useful when volunteered, never asked for on their own.
    SlotSpec("current_medicines", "Medicines currently taken", False),
    SlotSpec("previous_surgeries", "Previous operations", False),
    SlotSpec("weight", "Approximate weight", False),
    SlotSpec("height", "Approximate height", False),
]

DEPARTMENT_SLOTS: Dict[Department, List[SlotSpec]] = {
    Department.ORTHOPEDICS: [
        SlotSpec("pain_location", "Exact joint/bone/region affected", False),
        SlotSpec("injury_history", "Injury, fall or accident that started it", False),
        SlotSpec("functional_impact", "Walking, stairs, grip, daily activity impact", False),
        SlotSpec("imaging_done", "X-ray / MRI / scans already done", False),
    ],
    Department.GYNECOLOGY: [
        SlotSpec("menstrual_history", "LMP, cycle regularity, flow, pain", False),
        SlotSpec("pregnancy_possibility", "Any chance of current pregnancy", False),
        SlotSpec("obstetric_history", "Pregnancies, deliveries, miscarriages", False),
        SlotSpec("associated_symptoms", "Discharge, urinary symptoms, pelvic pain pattern", False),
    ],
}


@dataclass
class Slot:
    spec: SlotSpec
    value: Optional[str] = None
    updated_turn: int = 0

    @property
    def filled(self) -> bool:
        return bool(self.value and self.value.strip())


def slot_keys_for(department: Department) -> List[str]:
    return [s.key for s in COMMON_SLOTS + DEPARTMENT_SLOTS[department]]


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str
    interrupted: bool = False


class ConversationMemory:
    def __init__(
        self,
        *,
        consultation_id: uuid.UUID,
        department: Department,
        patient_info: Dict[str, Any],
    ) -> None:
        self.consultation_id = consultation_id
        self.department = department
        self.patient_info = patient_info
        self.turns: List[Turn] = []
        self.slots: Dict[str, Slot] = {
            spec.key: Slot(spec) for spec in COMMON_SLOTS + DEPARTMENT_SLOTS[department]
        }
        self.symptoms: List[Dict[str, Any]] = []
        self.deterministic_flags: List[str] = []
        self.llm_flags: List[str] = []
        self.emergency: bool = False
        self.model_says_complete: bool = False
        self.language: str = "en"
        self.medical_json: Optional[Dict[str, Any]] = None
        self.ledger = CostLedger()
        self.lock = asyncio.Lock()

    # -- turn tracking -------------------------------------------------------
    def add_patient_turn(self, text: str) -> None:
        self.turns.append(Turn("user", text))

    def add_assistant_turn(self, text: str, *, interrupted: bool = False) -> None:
        self.turns.append(Turn("assistant", text, interrupted=interrupted))

    @property
    def patient_turn_count(self) -> int:
        return sum(1 for t in self.turns if t.role == "user")

    # -- slot / coverage -----------------------------------------------------
    def update_slots(self, updates: Dict[str, Optional[str]]) -> None:
        for key, value in updates.items():
            slot = self.slots.get(key)
            if slot is None or value is None or not str(value).strip():
                continue
            slot.value = str(value).strip()
            slot.updated_turn = len(self.turns)

    def add_flags(self, flags: List[str], *, source: str) -> None:
        target = self.deterministic_flags if source == "deterministic" else self.llm_flags
        for flag in flags:
            if flag not in target:
                target.append(flag)

    @property
    def all_flags(self) -> List[str]:
        return list(dict.fromkeys(self.deterministic_flags + self.llm_flags))

    def coverage(self) -> Dict[str, Any]:
        required = [s for s in self.slots.values() if s.spec.required]
        filled = [s for s in required if s.filled]
        return {
            "required_total": len(required),
            "required_filled": len(filled),
            "missing_required": [s.spec.key for s in required if not s.filled],
            "ratio": round(len(filled) / len(required), 2) if required else 1.0,
        }

    def checklist_text(self) -> str:
        lines = []
        for slot in self.slots.values():
            mark = "COLLECTED" if slot.filled else ("MISSING*" if slot.spec.required else "missing")
            value = f" -> {slot.value[:80]}" if slot.filled and slot.value else ""
            lines.append(f"- [{mark}] {slot.spec.key}: {slot.spec.label}{value}")
        return "\n".join(lines)

    def known_facts_digest(self) -> str:
        """Compact structured digest — the long-term memory that survives the
        rolling verbatim window, so nothing said early is ever forgotten."""
        facts = [
            f"{slot.spec.label}: {slot.value}" for slot in self.slots.values() if slot.filled
        ]
        if self.symptoms:
            names = ", ".join(str(s.get("name", "")) for s in self.symptoms[:12] if s.get("name"))
            if names:
                facts.append(f"Reported symptoms: {names}")
        if self.all_flags:
            facts.append(f"Red flags noted: {', '.join(self.all_flags)}")
        return "\n".join(f"- {fact}" for fact in facts) if facts else "- Nothing collected yet."

    # -- completeness (deterministic authority) ------------------------------
    @property
    def required_coverage_met(self) -> bool:
        return not self.coverage()["missing_required"]

    @property
    def turn_budget_exhausted(self) -> bool:
        return self.patient_turn_count >= settings.MAX_PATIENT_TURNS

    @property
    def is_complete(self) -> bool:
        if self.emergency:
            return True
        if self.turn_budget_exhausted:
            return True
        return self.required_coverage_met and self.model_says_complete

    @property
    def should_wrap_up(self) -> bool:
        """Signal to the Conversation AI that it must close on this turn."""
        return self.emergency or self.turn_budget_exhausted or self.required_coverage_met

    # -- views ---------------------------------------------------------------
    def chat_window(self) -> List[Dict[str, str]]:
        """Rolling verbatim window; earlier context persists via the digest."""
        window = self.turns[-settings.MEMORY_VERBATIM_TURNS :]
        return [{"role": t.role, "content": t.content} for t in window]

    def transcript_text(self) -> str:
        lines = []
        for turn in self.turns:
            speaker = "Patient" if turn.role == "user" else "Satya Assistant"
            suffix = " [interrupted]" if turn.interrupted else ""
            lines.append(f"{speaker}: {turn.content}{suffix}")
        return "\n".join(lines)

    def meta(self) -> Dict[str, Any]:
        return {
            "patient_turns": self.patient_turn_count,
            "total_turns": len(self.turns),
            "coverage": self.coverage(),
            "emergency_detected": self.emergency,
            "deterministic_flags": self.deterministic_flags,
            "llm_flags": self.llm_flags,
            "language": self.language,
            "usage": self.ledger.snapshot(),
        }
