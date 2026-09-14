"""Sarvam streaming speech-to-text over WebSocket.

Protocol (per docs.sarvam.ai speech-to-text/ws):
- Connect with the `Api-Subscription-Key` header; model/language via query params.
- Send audio as JSON messages: {"audio": {"data": <base64 pcm16>, "sample_rate": ..., "encoding": ...}}.
- Receive JSON events; transcript events look like
  {"type": "data", "data": {"transcript": "...", ...}} — Sarvam's built-in VAD
  segments utterances, so each transcript event is a finalized utterance.
"""
import asyncio
import base64
import json
import string
import unicodedata
import urllib.parse
from typing import AsyncIterator, Optional

import websockets
from websockets.asyncio.client import ClientConnection, connect as ws_connect

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def is_hindi_english_text(text: str) -> bool:
    """Return whether text uses only Hindi or English characters."""
    has_letter = False
    for character in text:
        codepoint = ord(character)
        if "A" <= character <= "Z" or "a" <= character <= "z":
            has_letter = True
            continue
        if 0x0900 <= codepoint <= 0x097F:
            has_letter = True
            continue
        if character in string.digits or character in string.punctuation or character.isspace():
            continue
        if character in "\u200c\u200d" or unicodedata.category(character).startswith("M"):
            continue
        return False
    return has_letter


class SarvamSTTStream:
    def __init__(self, *, sample_rate: Optional[int] = None) -> None:
        self.sample_rate = sample_rate or settings.INPUT_AUDIO_SAMPLE_RATE
        self._ws: Optional[ClientConnection] = None
        self._closed = asyncio.Event()

    @property
    def url(self) -> str:
        params = {
            "language-code": settings.SARVAM_STT_LANGUAGE,
            "model": settings.SARVAM_STT_MODEL,
            "mode": settings.SARVAM_STT_MODE,
            "input_audio_codec": "pcm_s16le",
            "sample_rate": str(self.sample_rate),
        }
        return f"{settings.SARVAM_STT_WS_URL}?{urllib.parse.urlencode(params)}"

    async def connect(self) -> None:
        self._ws = await ws_connect(
            self.url,
            additional_headers={"Api-Subscription-Key": settings.SARVAM_API_KEY},
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        )
        logger.info("sarvam_stt_connected")

    async def send_audio(self, pcm16: bytes) -> None:
        if self._ws is None or self._closed.is_set():
            return
        message = {
            "audio": {
                "data": base64.b64encode(pcm16).decode("ascii"),
                "sample_rate": self.sample_rate,
                "encoding": "audio/wav",
            }
        }
        try:
            await self._ws.send(json.dumps(message))
        except websockets.ConnectionClosed:
            self._closed.set()

    async def transcripts(self) -> AsyncIterator[str]:
        """Yield finalized utterance transcripts as Sarvam's VAD emits them."""
        if self._ws is None:
            raise RuntimeError("SarvamSTTStream.connect() must be called first")
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == "data":
                    transcript = (event.get("data") or {}).get("transcript", "")
                    transcript = transcript.strip()
                    if transcript and is_hindi_english_text(transcript):
                        yield transcript
                    elif transcript:
                        logger.info("stt_transcript_discarded_non_hindi_english", extra={"text": transcript[:80]})
                elif event_type == "error":
                    logger.error("sarvam_stt_error", extra={"event": event})
        except websockets.ConnectionClosed as exc:
            logger.info("sarvam_stt_closed", extra={"code": exc.code, "reason": exc.reason})
        finally:
            self._closed.set()

    async def close(self) -> None:
        self._closed.set()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 - best-effort close
                pass
            self._ws = None
