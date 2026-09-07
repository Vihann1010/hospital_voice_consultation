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


class SarvamTTSStream:
    def __init__(self) -> None:
        self._ws: Optional[ClientConnection] = None
        self._text_done = False

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
        try:
            await self._ws.send(json.dumps({"type": "flush"}))
        except websockets.ConnectionClosed:
            pass

    async def audio_chunks(self) -> AsyncIterator[bytes]:
        """Yield raw PCM16 audio chunks as they are synthesized."""
        if self._ws is None:
            raise RuntimeError("SarvamTTSStream.connect() must be called first")
        try:
            async for raw in self._ws:
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
        except websockets.ConnectionClosed:
            pass

    async def close(self) -> None:
        if self._ws is not None:
            ws, self._ws = self._ws, None
            try:
                await asyncio.wait_for(ws.close(), timeout=2.0)
            except Exception:  # noqa: BLE001 - best-effort close
                pass
