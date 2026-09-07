"""Staff dictation WebSocket.

Reuses the Sarvam streaming STT client built for patient intake, but
authenticated with a staff access token instead of a patient session token.
Audio in, transcripts out; the client accumulates them and sends the finished
text to /prescriptions/dictation for structuring.
"""
import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.ai.sarvam_stt import SarvamSTTStream
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import TOKEN_TYPE_ACCESS

logger = get_logger(__name__)
router = APIRouter()


def _authenticate(token: str) -> bool:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return False
    return payload.get("type") == TOKEN_TYPE_ACCESS


@router.websocket("/ws/dictation")
async def dictation_socket(websocket: WebSocket, token: str = Query(...)) -> None:
    if not _authenticate(token):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    stt = SarvamSTTStream()
    try:
        await stt.connect()
        await websocket.send_json(
            {"type": "ready", "input_sample_rate": settings.INPUT_AUDIO_SAMPLE_RATE}
        )
    except Exception:  # noqa: BLE001
        logger.exception("dictation_stt_connect_failed")
        await websocket.send_json(
            {"type": "error", "message": "Speech recognition is unavailable right now."}
        )
        await websocket.close()
        return

    async def pump_transcripts() -> None:
        async for utterance in stt.transcripts():
            await websocket.send_json({"type": "transcript", "text": utterance})

    import asyncio

    reader = asyncio.create_task(pump_transcripts())
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"]:
                await stt.send_audio(message["bytes"])
            elif "text" in message and message["text"]:
                if '"stop"' in message["text"]:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("dictation_socket_error")
    finally:
        reader.cancel()
        await stt.close()
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
