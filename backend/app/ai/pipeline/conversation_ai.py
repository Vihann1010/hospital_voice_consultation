"""Conversation AI — the voice of the intake call.

Streams a structured `ConversationTurnPlan` per turn. The prompt is rebuilt
every turn from live memory: the slot checklist (collected vs missing), the
fact digest, red-flag state, and a deterministic directive telling the model
whether to keep exploring or wrap up — so the model always knows exactly
where the interview stands and when enough has been collected.
"""

from typing import AsyncIterator, Optional

from app.ai.pipeline.base_service import parse_json_object
from app.ai.pipeline.schemas import ConversationTurnPlan
from app.ai.prompts import GENERIC_DOCTOR
from app.ai.providers.factory import LLMGateway, get_gateway
from app.ai.session.memory import ConversationMemory
from app.ai.streaming_json import UtteranceStreamExtractor
from app.core.config import settings
from app.core.logging import get_logger
from app.departments import profile_for

logger = get_logger(__name__)

_TURN_JSON_CONTRACT = """The "utterance" field is READ ALOUD TO THE PATIENT WORD FOR WORD.
It must therefore contain ONLY what you would say to a patient: no instructions,
no field names, no checklist items, no English labels, no brackets, no slashes,
no quotation marks around it, nothing copied from the text above. If any of
those appear in "utterance", the patient hears them.

Reply with EXACTLY one JSON object, nothing else, with the keys IN THIS ORDER ("utterance" MUST be first — speech synthesis starts from it while you are still writing):
{"utterance": "<one or two short spoken sentences, in the patient's language, that a person would naturally say aloud>",
 "language": "en" | "hi" | "mixed",
 "phase": "greeting" | "exploring" | "clarifying" | "wrapping_up" | "emergency",
 "topics_addressed": ["<slot keys you asked about or acknowledged this turn>"],
 "conversation_complete": true | false,
 "handoff_note": null | "<one short sentence for the doctor, only when wrapping up>"}"""


def _persona(memory: ConversationMemory) -> str:
    dept = memory.department
    profile = profile_for(dept)
    doctor = memory.doctor_name or GENERIC_DOCTOR
    p = memory.patient_info
    return f"""You are the voice intake assistant of Satya Hospital, preparing {doctor}'s next consultation. You are on a live voice call; everything in "utterance" is spoken aloud.

Registered patient: {p.get('name')} — age {p.get('age')}, gender {p.get('gender')}, department {profile.label}.

Style: a kind, experienced nurse. One question at a time. Acknowledge before asking. Mirror the patient's language (Hindi / Hinglish / simple Indian English). Never repeat an already-answered question — the checklist below shows what is already collected. Probe a vague answer once, then move on. Never diagnose or prescribe; say the doctor will advise after seeing them.

{profile.intake_guide}"""


def _turn_directive(memory: ConversationMemory) -> str:
    coverage = memory.coverage()
    if memory.emergency:
        directive = (
            "EMERGENCY MODE: red flags detected "
            f"({', '.join(memory.all_flags)}). In your utterance, calmly tell the patient to "
            "come to Satya Hospital's emergency department immediately (or call for help if they "
            "cannot travel), keep it short and reassuring, set phase=\"emergency\" and "
            "conversation_complete=true. Do not ask further intake questions."
        )
    elif memory.should_wrap_up:
        directive = (
            "All required information is collected (or the interview limit is reached). "
            "WRAP UP NOW: in one or two sentences, summarise the key points back to the patient, "
            "tell them the doctor will see them shortly, thank them, set phase=\"wrapping_up\" "
            "and conversation_complete=true, and fill handoff_note."
        )
    else:
        missing = ", ".join(coverage["missing_required"][:3])
        directive = (
            f"Continue the interview. Still needed: {missing}. "
            "Ask ONE short question about the most natural of these. "
            "Set conversation_complete=false."
        )
    return f"""CURRENT INTERVIEW STATE
Patient turns so far: {memory.patient_turn_count} (hard limit {settings.MAX_PATIENT_TURNS})
Known facts:
{memory.known_facts_digest()}

Collection checklist (* = required):
{memory.checklist_text()}

DIRECTIVE FOR THIS TURN: {directive}

{_TURN_JSON_CONTRACT}"""


class ConversationAIService:
    stage = "conversation_ai"

    def __init__(self, gateway: Optional[LLMGateway] = None) -> None:
        self.gateway = gateway or get_gateway()
        self.last_plan: Optional[ConversationTurnPlan] = None

    async def stream_utterance(
        self, memory: ConversationMemory
    ) -> AsyncIterator[str]:
        """Yield spoken utterance chunks; sets `self.last_plan` when finished."""
        self.last_plan: Optional[ConversationTurnPlan] = None
        window = memory.chat_window()
        # A conversation ending on the assistant's own turn is refused outright
        # by Gemini ("Requests ending with a model turn are not supported"),
        # which silenced the intake. Turn order is fixed at the source; this
        # keeps any other path from reaching the model in that shape.
        if window and window[-1]["role"] == "assistant":
            window.append({
                "role": "user",
                "content": "(The patient has not said anything further. Continue the interview.)",
            })
        messages = [
            {"role": "system", "content": _persona(memory)},
            *window,
            {"role": "system", "content": _turn_directive(memory)},
        ]
        if not memory.turns:
            messages.append(
                {"role": "user", "content": "(The call has connected. Greet the patient and begin.)"}
            )

        extractor = UtteranceStreamExtractor()
        async for delta in self.gateway.stream(
            messages,
            stage=self.stage,
            tier="dialogue",
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            json_mode=True,
            ledger=memory.ledger,
            tag=str(memory.consultation_id),
        ):
            spoken = extractor.feed(delta)
            if spoken:
                yield spoken

        # Well-formed JSON has already streamed. A plain-text reply is held
        # back until the whole turn can be judged, and released here — or
        # withheld entirely if the model was narrating its own output.
        trailing = extractor.finish()
        if trailing:
            yield trailing

        self.last_plan = self._finalize_plan(extractor, memory)

    def _finalize_plan(
        self, extractor: UtteranceStreamExtractor, memory: ConversationMemory
    ) -> ConversationTurnPlan:
        # A reply cut off by the token limit leaves unparseable JSON, but the
        # utterance itself streamed out first and was already spoken. Recover
        # it so the turn is recorded as what the patient actually heard.
        payload = parse_json_object(extractor.raw)
        if payload is None and not extractor.suppressed:
            partial = UtteranceStreamExtractor()
            recovered = (partial.feed(extractor.raw) + partial.finish()).strip()
            if recovered:
                logger.warning(
                    "turn_plan_truncated",
                    extra={"consultation_id": str(memory.consultation_id),
                           "recovered_chars": len(recovered)},
                )
                return ConversationTurnPlan(
                    utterance=recovered,
                    conversation_complete=memory.should_wrap_up,
                    phase="emergency" if memory.emergency else "exploring",
                )
        if payload is not None:
            try:
                plan = ConversationTurnPlan.model_validate(payload)
                if plan.utterance.strip():
                    return plan
            except Exception:  # noqa: BLE001 - fall through to salvage
                pass
        # Salvage: whatever was actually spoken is the utterance of record.
        spoken = extractor.raw.strip() if extractor.passthrough else ""
        if not spoken:
            fresh = UtteranceStreamExtractor()
            spoken = fresh.feed(extractor.raw)
        logger.warning(
            "turn_plan_salvaged",
            extra={"consultation_id": str(memory.consultation_id), "raw_head": extractor.raw[:120]},
        )
        return ConversationTurnPlan(
            utterance=spoken.strip(),
            conversation_complete=memory.should_wrap_up,
            phase="emergency" if memory.emergency else "exploring",
        )
