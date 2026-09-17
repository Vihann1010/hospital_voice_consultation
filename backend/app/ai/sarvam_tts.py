"""Sarvam streaming text-to-speech over WebSocket (bulbul).

Protocol (per docs.sarvam.ai text-to-speech/ws):
- Connect with `Api-Subscription-Key` header; model via query param.
- First message must be a config frame:
    {"type": "config", "data": {target_language_code, speaker, min_buffer_size,
                                 max_chunk_length, output_audio_codec, ...}}
- Then text frames: {"type": "text", "data": {"text": "..."}}
- {"type": "flush"} forces synthesis of whatever is buffered.
- Server sends {"type": "audio", "data": {"audio": <base64>}} chunks.

One connection is opened per assistant reply so that interruption can simply
close the socket, guaranteeing no stale audio arrives afterwards.
"""
import asyncio
import base64
import json
import urllib.parse
from typing import AsyncIterator, Optional

import websockets
from websockets.asyncio.client import ClientConnection, connect as ws_connect

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# After the flush, this much silence from Sarvam means the reply is complete.
# Long enough to cover synthesis of a trailing sentence, short enough that the
# assistant stops "holding the floor" soon after the patient stops hearing it.
TTS_IDLE_END_S = 2.5


def _is_final(event: dict) -> bool:
    """Did Sarvam say the flushed text is fully synthesized?"""
    kind = str(event.get("type") or "").lower()
    if kind in ("final", "completed", "complete", "done", "end"):
        return True
    detail = event.get("data") if isinstance(event.get("data"), dict) else {}
    marker = str(detail.get("event_type") or detail.get("event") or "").lower()
    return kind == "event" and marker in ("final", "completed", "complete", "done", "end")


class SarvamTTSStream:
    def __init__(self) -> None:
        self._ws: Optional[ClientConnection] = None
        self._text_done = False
        # Set once all the text has been sent and synthesis asked to finish.
        # From then on, silence means the reply is over.
        self._flushed = False

    @property
    def url(self) -> str:
        params = {"model": settings.SARVAM_TTS_MODEL}
        return f"{settings.SARVAM_TTS_WS_URL}?{urllib.parse.urlencode(params)}"

    async def connect(self) -> None:
        self._ws = await ws_connect(
            self.url,
            additional_headers={"Api-Subscription-Key": settings.SARVAM_API_KEY},
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        )
        config = {
            "type": "config",
            "data": {
                "target_language_code": settings.SARVAM_TTS_LANGUAGE,
                "speaker": settings.SARVAM_TTS_SPEAKER,
                "pitch": 0.0,
                "pace": 1.0,
                "loudness": 1.0,
                "speech_sample_rate": settings.SARVAM_TTS_SAMPLE_RATE,
                "min_buffer_size": 40,
                "max_chunk_length": 200,
                "output_audio_codec": "linear16",
                "enable_preprocessing": True,
            },
        }
        await self._ws.send(json.dumps(config))

    async def send_text(self, text: str) -> None:
        if self._ws is None or not text:
            return
        try:
            await self._ws.send(json.dumps({"type": "text", "data": {"text": text}}))
        except websockets.ConnectionClosed:
            pass

    async def flush(self) -> None:
        if self._ws is None:
            return
        self._flushed = True
        try:
            await self._ws.send(json.dumps({"type": "flush"}))
        except websockets.ConnectionClosed:
            pass

    async def audio_chunks(self) -> AsyncIterator[bytes]:
        """Yield raw PCM16 audio chunks as they are synthesized.

        Ends when Sarvam reports the flushed text finished, or when no audio
        has arrived for `TTS_IDLE_END_S` after the flush. Sarvam does not close
        the socket after a flush, and reading until it did left every reply
        waiting out a twenty-second timeout — during which the server treated
        the patient's every answer as talking over the assistant.
        """
        if self._ws is None:
            raise RuntimeError("SarvamTTSStream.connect() must be called first")
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=TTS_IDLE_END_S if self._flushed else None,
                    )
                except asyncio.TimeoutError:
                    return
                if isinstance(raw, bytes):
                    yield raw
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == "audio":
                    b64_audio = (event.get("data") or {}).get("audio")
                    if b64_audio:
                        yield base64.b64decode(b64_audio)
                elif event_type == "error":
                    logger.error("sarvam_tts_error", extra={"event": event})
                elif _is_final(event):
                    return
        except websockets.ConnectionClosed:
            pass

    async def close(self) -> None:
        if self._ws is not None:
            ws, self._ws = self._ws, None
            try:
                await asyncio.wait_for(ws.close(), timeout=2.0)
            except Exception:  # noqa: BLE001 - best-effort close
                pass
