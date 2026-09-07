"""Realtime voice pipeline for one consultation session (Phase 2).

Same wire protocol and public API as Phase 1 — but the brain is now the
service pipeline:

  mic ─► Sarvam STT ─► utterance
      ├─ layer-1 emergency screen (deterministic, instant)
      ├─ Symptom Extractor (fast tier, background)  ─► slot coverage
      └─ Conversation AI (streaming structured JSON) ─► sentences ─► Sarvam TTS

Continuity + interruption semantics are unchanged: audio never stops flowing
to STT; a new utterance or client VAD cancels in-flight speech instantly and
the partial reply is persisted with interrupted=True.
"""
import asyncio
import contextlib
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.ai.pipeline.conversation_ai import ConversationAIService
from app.ai.echo import is_echo
from app.ai.pipeline.pipeline import clinical_pipeline
from app.ai.sarvam_stt import SarvamSTTStream
from app.ai.sarvam_tts import SarvamTTSStream
from app.ai.session.manager import session_manager
from app.ai.session.memory import ConversationMemory
from app.core.config import settings
from app.core.logging import get_logger
from app.models.consultation import Consultation, ConversationTurn
from app.models.enums import TurnRole
from app.models.patient import Patient

logger = get_logger(__name__)

SENTENCE_END = re.compile(r"([.!?।]+[\"')\]]?\s+)")
UTTERANCE_MERGE_WINDOW_S = 0.7

SendJson = Callable[[Dict[str, Any]], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]
RecordTurn = Callable[..., Awaitable[Any]]
SaveMedicalJson = Callable[[Dict[str, Any]], Awaitable[None]]


class VoiceSession:
    def __init__(
        self,
        *,
        consultation: Consultation,
        patient: Patient,
        previous_turns: List[ConversationTurn],
        send_json: SendJson,
        send_audio: SendBytes,
        record_turn: RecordTurn,
        save_medical_json: SaveMedicalJson,
    ) -> None:
        self.consultation_id: uuid.UUID = consultation.id
        self.department = consultation.department
        self.patient = patient
        self.previous_turns = previous_turns
        self.send_json = send_json
        self.send_audio = send_audio
        self.record_turn = record_turn
        self.save_medical_json = save_medical_json

        self.memory: Optional[ConversationMemory] = None
        self.conversation = ConversationAIService()

        self.stt = SarvamSTTStream()
        self._speak_task: Optional[asyncio.Task] = None
        self._pending_utterance_task: Optional[asyncio.Task] = None
        self._pending_utterances: List[str] = []
        self._ingest_tasks: set[asyncio.Task] = set()
        self._stt_reader_task: Optional[asyncio.Task] = None
        self._speaking = asyncio.Event()
        # What the assistant is saying (or just said), used to recognise its
        # own voice arriving back through the microphone.
        self._current_utterance = ""
        self._speech_started_at = 0.0
        self._speech_ended_at = 0.0
        self._stopped = False
        self._queue_lock = asyncio.Lock()
        self._turns_since_record = 0

    # ------------------------------------------------------------------ setup
    def _build_memory(self) -> ConversationMemory:
        memory = ConversationMemory(
            consultation_id=self.consultation_id,
            department=self.department,
            patient_info={
                "name": self.patient.name,
                "age": self.patient.age,
                "gender": self.patient.gender.value,
                "phone_number": self.patient.phone_number,
            },
        )
        for turn in self.previous_turns:  # rebuild context after a reconnect
            if turn.role == TurnRole.PATIENT:
                memory.add_patient_turn(turn.content)
            else:
                memory.add_assistant_turn(turn.content, interrupted=turn.interrupted)
        return memory

    async def start(self) -> None:
        self.memory = await session_manager.acquire(
            self.consultation_id, factory=self._build_memory
        )
        await self.stt.connect()
        self._stt_reader_task = asyncio.create_task(self._consume_transcripts())
        await self.send_json(
            {
                "type": "session_ready",
                "tts_sample_rate": settings.SARVAM_TTS_SAMPLE_RATE,
                "input_sample_rate": settings.INPUT_AUDIO_SAMPLE_RATE,
            }
        )
        if not self.memory.turns:  # brand-new session: assistant opens the call
            greeting = (settings.GREETING_TEXT or "").strip()
            if settings.GREETING_ENABLED and greeting:
                # Fixed opening: instant, costs no tokens, and still works when
                # the model is unavailable.
                self._speak_task = asyncio.create_task(
                    self._speak_reply(fixed_text=greeting)
                )
            else:
                self._speak_task = asyncio.create_task(self._speak_reply())

    # ------------------------------------------------------- inbound from client
    async def on_audio(self, pcm16: bytes) -> None:
        # Audio is streamed to speech recognition and not retained: the stored
        # record of a consultation is its transcript, not its audio.
        await self.stt.send_audio(pcm16)

    async def on_interrupt(self) -> None:
        """Client-side VAD detected the patient talking over the assistant."""
        await self._cancel_speaking(reason="client_vad")

    def _reject_as_echo(self, utterance: str) -> bool:
        """True when this transcript is the assistant's own voice.

        Only consulted while the assistant holds the floor, or just after, so
        ordinary patient speech is never measured against a stale sentence.
        """
        if not settings.ECHO_REJECTION_ENABLED:
            return False
        speaking = self._speaking.is_set()
        in_tail = (
            not speaking
            and self._speech_ended_at
            and (time.monotonic() - self._speech_ended_at) < settings.ECHO_TAIL_S
        )
        if not (speaking or in_tail):
            return False
        return is_echo(utterance, self._current_utterance)

    # ------------------------------------------------------------- STT pipeline
    async def _consume_transcripts(self) -> None:
        try:
            async for utterance in self.stt.transcripts():
                if self._stopped or self.memory is None:
                    break
                await session_manager.touch(self.consultation_id)

                # Discard the assistant's own voice before it does any damage:
                # not merely ignored for interruption, but dropped entirely, so
                # it never reaches the transcript or the medical record.
                if self._reject_as_echo(utterance):
                    logger.info(
                        "echo_discarded",
                        extra={"consultation_id": str(self.consultation_id),
                               "text": utterance[:80]},
                    )
                    continue

                logger.info(
                    "utterance",
                    extra={"consultation_id": str(self.consultation_id), "text": utterance},
                )
                await self.send_json({"type": "final_transcript", "text": utterance})

                # Layer-1 emergency screen — instant, before anything else.
                new_emergency = clinical_pipeline.screen_deterministic(self.memory, utterance)
                if new_emergency:
                    await self.send_json(
                        {"type": "emergency_detected", "flags": self.memory.deterministic_flags}
                    )

                if self._speaking.is_set():
                    # Genuine speech during playback is a barge-in — but not in
                    # the first moments, where a late echo of the assistant's
                    # opening words is the likelier explanation.
                    elapsed = time.monotonic() - self._speech_started_at
                    if elapsed >= settings.BARGE_IN_GRACE_S:
                        await self._cancel_speaking(reason="patient_spoke")
                    else:
                        logger.info(
                            "barge_in_suppressed_in_grace",
                            extra={"consultation_id": str(self.consultation_id),
                                   "elapsed_s": round(elapsed, 2)},
                        )

                async with self._queue_lock:
                    self._pending_utterances.append(utterance)
                    if self._pending_utterance_task is not None:
                        self._pending_utterance_task.cancel()
                    self._pending_utterance_task = asyncio.create_task(
                        self._debounced_respond(immediate=new_emergency)
                    )
        except Exception:
            if not self._stopped:
                logger.exception("stt_reader_failed")
                await self.send_json(
                    {"type": "error", "message": "Speech recognition dropped. Please refresh to continue."}
                )

    async def _debounced_respond(self, *, immediate: bool = False) -> None:
        """Merge rapid fragments, persist the patient turn, launch reply + analysis."""
        if not immediate:
            try:
                await asyncio.sleep(UTTERANCE_MERGE_WINDOW_S)
            except asyncio.CancelledError:
                return
        async with self._queue_lock:
            text = " ".join(self._pending_utterances).strip()
            self._pending_utterances.clear()
        if not text or self._stopped or self.memory is None:
            return

        await self.record_turn(role=TurnRole.PATIENT, content=text)
        self.memory.add_patient_turn(text)

        # Symptom extraction runs concurrently with the spoken reply so the
        # voice never waits on analysis (its slot updates inform the *next* turn).
        self._spawn_ingest(text)

        if self._speak_task is not None and not self._speak_task.done():
            await self._cancel_speaking(reason="new_utterance")
        self._speak_task = asyncio.create_task(self._speak_reply())

    def _spawn_ingest(self, text: str) -> None:
        async def ingest() -> None:
            assert self.memory is not None
            await clinical_pipeline.ingest_patient_turn(self.memory, text)
            self._turns_since_record += 1
            if (
                self._turns_since_record >= settings.MEDICAL_JSON_EVERY_N_TURNS
                and not self._stopped
            ):
                self._turns_since_record = 0
                record = await clinical_pipeline.refresh_medical_record(self.memory)
                if record is not None and not self._stopped:
                    await self.save_medical_json(record.model_dump())
                    await self.send_json({"type": "medical_json", "data": record.model_dump()})

        task = asyncio.create_task(ingest())
        self._ingest_tasks.add(task)
        task.add_done_callback(self._ingest_tasks.discard)

    # ---------------------------------------------------------- speak one turn
    async def _speak_reply(self, fixed_text: Optional[str] = None) -> None:
        """Speak one assistant turn.

        With `fixed_text`, the text is spoken verbatim and no model is called —
        used for the opening greeting. Otherwise the reply streams from the
        conversation model as usual.
        """
        assert self.memory is not None
        tts = SarvamTTSStream()
        spoken_text = ""
        interrupted = False
        forward_task: Optional[asyncio.Task] = None
        try:
            self._speaking.set()
            self._speech_started_at = time.monotonic()
            self._current_utterance = ""
            await self.send_json({"type": "assistant_start"})
            await tts.connect()

            async def forward_audio() -> None:
                async for chunk in tts.audio_chunks():
                    await self.send_audio(chunk)

            forward_task = asyncio.create_task(forward_audio())

            async def fixed_source():
                yield fixed_text

            source = (
                fixed_source()
                if fixed_text is not None
                else self.conversation.stream_utterance(self.memory)
            )

            buffer = ""
            async for spoken in source:
                spoken_text += spoken
                self._current_utterance = spoken_text
                buffer += spoken
                await self.send_json({"type": "assistant_delta", "text": spoken})
                while True:
                    match = SENTENCE_END.search(buffer)
                    if match is None:
                        break
                    cut = match.end()
                    sentence, buffer = buffer[:cut], buffer[cut:]
                    await tts.send_text(sentence)
            if buffer.strip():
                await tts.send_text(buffer)
            await tts.flush()

            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(forward_task, timeout=20.0)
        except asyncio.CancelledError:
            interrupted = True
            raise
        except Exception:
            logger.exception("speak_reply_failed")
            await self.send_json(
                {"type": "error", "message": "Voice reply failed. You can keep talking — I'm still listening."}
            )
        finally:
            if forward_task is not None and not forward_task.done():
                forward_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await forward_task
            await tts.close()
            self._speaking.clear()
            self._speech_ended_at = time.monotonic()
            await self._finish_assistant_turn(spoken_text, interrupted)

    async def _finish_assistant_turn(self, text: str, interrupted: bool) -> None:
        if self.memory is None:
            return
        text = text.strip()
        plan = self.conversation.last_plan
        if text:
            self.memory.add_assistant_turn(text, interrupted=interrupted)
            with contextlib.suppress(Exception):
                await self.record_turn(
                    role=TurnRole.ASSISTANT, content=text, interrupted=interrupted
                )
        if plan is not None and not interrupted:
            self.memory.model_says_complete = plan.conversation_complete
            self.memory.language = plan.language
        with contextlib.suppress(Exception):
            await self.send_json({"type": "assistant_end", "interrupted": interrupted})
            if self.memory.is_complete and not interrupted:
                await self.send_json(
                    {
                        "type": "conversation_complete",
                        "emergency": self.memory.emergency,
                        "coverage": self.memory.coverage(),
                    }
                )

    async def _cancel_speaking(self, *, reason: str) -> None:
        task = self._speak_task
        if task is None or task.done():
            return
        logger.info(
            "barge_in", extra={"consultation_id": str(self.consultation_id), "reason": reason}
        )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await self.send_json({"type": "interrupted"})

    # ----------------------------------------------------------- finalization
    async def final_medical_json(self) -> Optional[Dict[str, Any]]:
        """Run the full clinical pipeline; returns the dossier for persistence."""
        if self.memory is None:
            return None
        for task in list(self._ingest_tasks):  # let in-flight analysis land
            with contextlib.suppress(Exception):
                await task
        try:
            dossier = await clinical_pipeline.finalize(self.memory)
            return dossier.model_dump()
        except Exception:
            logger.exception(
                "pipeline_finalize_failed", extra={"consultation_id": str(self.consultation_id)}
            )
            return self.memory.medical_json
        finally:
            await session_manager.release(self.consultation_id, discard=True)

    # ------------------------------------------------------------------ teardown
    async def stop(self) -> None:
        self._stopped = True
        for task in (self._pending_utterance_task, self._speak_task, self._stt_reader_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await self.stt.close()
