"""Voice intake turn-taking: the faults behind the silenced intake of 13 Sep 2026.

No audio services are touched. The session's speech-recognition and
synthesis clients are constructed but never connected, and the model gateway
is replaced with one that records what it was asked.
"""
import asyncio
import time
import uuid
from types import SimpleNamespace

import pytest

from app.ai import sarvam_tts
from app.ai.orchestrator import VoiceSession
from app.ai.pipeline.conversation_ai import ConversationAIService
from app.ai.session.memory import ConversationMemory
from app.models.enums import Department, TurnRole

pytestmark = pytest.mark.unit


def _memory() -> ConversationMemory:
    return ConversationMemory(
        consultation_id=uuid.uuid4(),
        department=Department.ORTHOPEDICS,
        patient_info={"name": "Test", "age": 40, "gender": "male", "phone_number": "9000000000"},
    )


class _RecordingGateway:
    def __init__(self) -> None:
        self.messages = None

    async def stream(self, messages, **_kwargs):
        self.messages = messages
        yield '{"utterance": "ठीक है।", "language": "hi", "phase": "exploring", '
        yield '"topics_addressed": [], "conversation_complete": false, "handoff_note": null}'


# --------------------------------------------------------------- gateway guard
def test_a_conversation_ending_on_the_assistant_is_never_sent_that_way():
    """Gemini refuses a request whose last turn is the model's own."""
    memory = _memory()
    memory.add_patient_turn("मेरे घुटने में दर्द है।")
    memory.add_assistant_turn("कब से?", interrupted=True)
    gateway = _RecordingGateway()

    async def run():
        async for _ in ConversationAIService(gateway=gateway).stream_utterance(memory):
            pass

    asyncio.run(run())
    turns = [m for m in gateway.messages if m["role"] != "system"]
    assert turns[-1]["role"] == "user"


def test_a_normal_conversation_is_sent_unchanged():
    memory = _memory()
    memory.add_assistant_turn("बताइए?")
    memory.add_patient_turn("दर्द है।")
    gateway = _RecordingGateway()

    async def run():
        async for _ in ConversationAIService(gateway=gateway).stream_utterance(memory):
            pass

    asyncio.run(run())
    turns = [m for m in gateway.messages if m["role"] != "system"]
    assert [m["content"] for m in turns] == ["बताइए?", "दर्द है।"]


# ------------------------------------------------------------------ turn order
def _session(recorded):
    async def record_turn(*, role, content, interrupted=False):
        recorded.append((role, content, interrupted))

    async def send_json(_payload):
        return None

    async def send_audio(_chunk):
        return None

    async def save_medical_json(_record):
        return None

    session = VoiceSession(
        consultation=SimpleNamespace(id=uuid.uuid4(), department=Department.ORTHOPEDICS),
        patient=SimpleNamespace(name="Test", age=40, gender=SimpleNamespace(value="male"),
                                phone_number="9000000000"),
        previous_turns=[],
        send_json=send_json,
        send_audio=send_audio,
        record_turn=record_turn,
        save_medical_json=save_medical_json,
    )
    session.memory = _memory()
    session._spawn_ingest = lambda _text: None
    return session


def test_a_cut_off_reply_is_recorded_before_the_words_that_cut_it_off():
    recorded = []

    async def run():
        session = _session(recorded)

        async def reply_in_flight():
            try:
                session._speaking.set()
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await session._finish_assistant_turn("क्या आपको एलर्जी है?", True)
                raise
            finally:
                session._speaking.clear()

        async def next_reply():
            return None

        session._speak_task = asyncio.create_task(reply_in_flight())
        await asyncio.sleep(0)
        session._speak_reply = next_reply
        session._pending_utterances.append("नहीं है।")
        await session._debounced_respond(immediate=True)
        return session.memory.turns

    turns = asyncio.run(run())
    assert [role for role, _, _ in recorded] == [TurnRole.ASSISTANT, TurnRole.PATIENT]
    assert [turn.role for turn in turns] == ["assistant", "user"]


# ------------------------------------------------------------ audibility / TTS
def test_speech_after_the_audio_finished_playing_is_not_an_interruption():
    session = _session([])
    session._playback_ends_at = time.monotonic() - 0.5
    assert not session._audible()
    session._playback_ends_at = time.monotonic() + 1.5
    assert session._audible()


@pytest.mark.parametrize("event, final", [
    ({"type": "audio", "data": {"audio": "AAAA"}}, False),
    ({"type": "error", "data": {}}, False),
    ({"type": "event", "data": {"event_type": "final"}}, True),
    ({"type": "completed"}, True),
])
def test_tts_completion_markers(event, final):
    assert sarvam_tts._is_final(event) is final


class _SilentSocket:
    """Sends a few audio frames, then stays open and says nothing — as Sarvam does."""

    def __init__(self, frames):
        self._frames = list(frames)

    async def recv(self):
        if self._frames:
            return self._frames.pop(0)
        await asyncio.sleep(3600)


def test_the_audio_stream_ends_on_silence_after_a_flush(monkeypatch):
    monkeypatch.setattr(sarvam_tts, "TTS_IDLE_END_S", 0.2)
    stream = sarvam_tts.SarvamTTSStream()
    stream._ws = _SilentSocket([b"\x00\x01" * 10, b"\x00\x01" * 10])
    stream._flushed = True

    async def run():
        started = time.monotonic()
        chunks = [chunk async for chunk in stream.audio_chunks()]
        return chunks, time.monotonic() - started

    chunks, elapsed = asyncio.run(run())
    assert len(chunks) == 2
    assert elapsed < 2.0
