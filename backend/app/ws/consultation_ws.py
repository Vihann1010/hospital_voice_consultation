"""WebSocket endpoint that hosts one patient voice session.

Client -> server:
  binary frames : PCM16 mono audio at INPUT_AUDIO_SAMPLE_RATE
  {"type": "interrupt"} : local VAD heard the patient over assistant playback
  {"type": "end"}       : patient tapped "End consultation"

Server -> client:
  binary frames : PCM16 mono TTS audio at tts_sample_rate
  JSON events   : session_ready, final_transcript, assistant_start,
                  assistant_delta, assistant_end, interrupted, medical_json,
                  session_ended, error
"""
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.ai.orchestrator import VoiceSession
from app.core.logging import get_logger
from app.core.security import TOKEN_TYPE_CONSULTATION, decode_token
from app.db.session import AsyncSessionLocal
from app.models.enums import ConsultationStatus, TurnRole
from app.services.consultant_directory import department_doctor_name
from app.services.consultation_service import ConsultationService

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/consultations/{consultation_id}")
async def consultation_socket(
    websocket: WebSocket,
    consultation_id: uuid.UUID,
    token: str = Query(...),
) -> None:
    claims = decode_token(token)
    if (
        claims is None
        or claims.get("type") != TOKEN_TYPE_CONSULTATION
        or claims.get("consultation_id") != str(consultation_id)
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    async with AsyncSessionLocal() as session:
        service = ConsultationService(session)
        context = await service.get_session_context(consultation_id)
        if context is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        consultation, patient, previous_turns = context
        if consultation.status != ConsultationStatus.IN_PROGRESS:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        # Read once, here, while the session is open: the assistant names the
        # doctor out loud, and that name belongs to the consultant register.
        doctor_name = await department_doctor_name(session, consultation.department)

    send_failures: dict = {}

    def note_send_failure(kind: str, payload_type: str, exc: Exception) -> None:
        # Logged once per kind per session: a closed socket fails every send
        # after it, and one line saying so is enough.
        count = send_failures.get(kind, 0) + 1
        send_failures[kind] = count
        if count == 1:
            logger.warning(
                "voice_send_failed",
                extra={
                    "consultation_id": str(consultation_id),
                    "kind": kind,
                    "payload_type": payload_type,
                    "client_state": str(getattr(websocket, "client_state", "")),
                    "error": repr(exc),
                },
            )

    async def send_json(payload: dict) -> None:
        try:
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 - socket may already be gone
            note_send_failure("json", str(payload.get("type")), exc)

    async def send_audio(chunk: bytes) -> None:
        try:
            await websocket.send_bytes(chunk)
        except Exception as exc:  # noqa: BLE001
            note_send_failure("audio", "pcm", exc)

    async def record_turn(*, role: TurnRole, content: str, interrupted: bool = False):
        async with AsyncSessionLocal() as turn_session:
            return await ConsultationService(turn_session).record_turn(
                consultation_id=consultation_id,
                role=role,
                content=content,
                interrupted=interrupted,
            )

    async def save_medical_json(medical_json: dict) -> None:
        async with AsyncSessionLocal() as mj_session:
            await ConsultationService(mj_session).update_medical_json(
                consultation_id, medical_json
            )

    voice = VoiceSession(
        consultation=consultation,
        patient=patient,
        previous_turns=previous_turns,
        send_json=send_json,
        send_audio=send_audio,
        record_turn=record_turn,
        save_medical_json=save_medical_json,
        doctor_name=doctor_name,
    )

    ended_by_patient = False
    try:
        await voice.start()
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if (data := message.get("bytes")) is not None:
                await voice.on_audio(data)
                continue
            if (text := message.get("text")) is not None:
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == "interrupt":
                    await voice.on_interrupt()
                elif event_type == "end":
                    ended_by_patient = True
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception(
            "voice_session_crashed", extra={"consultation_id": str(consultation_id)}
        )
    finally:
        if send_failures:
            logger.warning(
                "voice_send_failures_total",
                extra={"consultation_id": str(consultation_id), "failures": send_failures},
            )
        await voice.stop()
        final_json = None
        try:
            final_json = await voice.final_medical_json()
        except Exception:
            logger.exception("final_extraction_failed")
        async with AsyncSessionLocal() as finalize_session:
            finalize_service = ConsultationService(finalize_session)
            final_status = (
                ConsultationStatus.COMPLETED if ended_by_patient else ConsultationStatus.ABANDONED
            )
            consultation_row = await finalize_service.finalize(
                consultation_id, medical_json=final_json, status=final_status
            )
        if ended_by_patient and consultation_row is not None:
            await send_json(
                {
                    "type": "session_ended",
                    "status": final_status.value,
                    "medical_json": consultation_row.medical_json,
                    "transcript": consultation_row.transcript,
                }
            )
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
