"""Copilot service — assembles the doctor's briefing and records their decisions.

The briefing is stored inside the consultation's existing `medical_json` JSONB
column under a `copilot` key, so no schema migration is required. Doctor
decisions (accept / dismiss) are stored alongside it: the AI's suggestion and
the clinician's judgement are kept as separate, auditable facts.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipeline.base_service import StageError
from app.ai.pipeline.copilot import CopilotAIService
from app.ai.pipeline.medication_rules import run_medication_rules
from app.ai.pipeline.schemas import CopilotBriefing
from app.core.logging import get_logger
from app.models.consultation import Consultation
from app.repositories.consultation_repository import ConsultationRepository

logger = get_logger(__name__)


def _medicine_names(medical_json: Dict[str, Any]) -> List[str]:
    record = medical_json.get("medical_json") or {}
    names: List[str] = []

    for item in record.get("current_medicines") or []:
        if isinstance(item, dict):
            name = item.get("name")
            dose = item.get("dose_or_frequency")

            if name:
                names.append(f"{name} {dose}".strip() if dose else str(name))

        elif isinstance(item, str):
            names.append(item)

    return names


def _allergies(medical_json: Dict[str, Any]) -> List[str]:
    record = medical_json.get("medical_json") or {}
    return [str(a) for a in (record.get("allergies") or []) if str(a).strip()]


class CopilotService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.consultations = ConsultationRepository(session)
        self.ai = CopilotAIService()

    async def get_or_build(
        self,
        consultation_id: uuid.UUID,
        *,
        refresh: bool = False,
    ) -> Optional[CopilotBriefing]:

        # IMPORTANT:
        # Load patient + turns eagerly to avoid async lazy-loading
        consultation = await self.consultations.get_with_details(
            consultation_id
        )

        if consultation is None:
            return None

        dossier: Dict[str, Any] = consultation.medical_json or {}

        cached = dossier.get("copilot")

        if cached and not refresh:
            try:
                return CopilotBriefing.model_validate(cached)
            except Exception:
                logger.warning(
                    "copilot_cache_invalid",
                    extra={
                        "consultation_id": str(consultation_id)
                    },
                )

        briefing = await self._build(
            consultation,
            dossier,
        )

        await self._persist(
            consultation,
            briefing,
            preserve=cached,
        )

        return briefing

    async def _build(
        self,
        consultation: Consultation,
        dossier: Dict[str, Any],
    ) -> CopilotBriefing:

        medicines = _medicine_names(dossier)
        allergies = _allergies(dossier)

        rule_alerts = run_medication_rules(
            medicines,
            allergies,
        )

        briefing = CopilotBriefing(
            generated_at=datetime.now(timezone.utc).isoformat(),
            medication_alerts=list(rule_alerts),
        )

        try:
            patient = consultation.patient

            ai_output = await self.ai.brief(
                department=consultation.department.value,
                patient={
                    "age": patient.age if patient else None,
                    "gender": (
                        patient.gender.value
                        if patient and patient.gender
                        else None
                    ),
                },
                dossier=dossier,
                medicines=medicines,
                allergies=allergies,
                rule_alerts=[
                    a.model_dump()
                    for a in rule_alerts
                ],
                tag=str(consultation.id),
            )

        except StageError as exc:
            logger.exception(
                "copilot_ai_failed",
                extra={
                    "consultation_id": str(consultation.id)
                },
            )

            briefing.errors.append(str(exc))
            return briefing

        for alert in ai_output.interaction_alerts:
            alert.detected_by = "ai"
            alert.kind = "interaction"

        briefing.medication_alerts.extend(
            ai_output.interaction_alerts
        )

        briefing.follow_up_questions = ai_output.follow_up_questions
        briefing.referrals = ai_output.referrals
        briefing.notes = ai_output.notes

        return briefing

    async def _persist(
        self,
        consultation: Consultation,
        briefing: CopilotBriefing,
        *,
        preserve: Optional[Dict[str, Any]] = None,
    ) -> None:

        dossier = dict(consultation.medical_json or {})

        payload = briefing.model_dump()

        if preserve and isinstance(
            preserve.get("decisions"),
            dict,
        ):
            payload["decisions"] = preserve["decisions"]

        dossier["copilot"] = payload

        consultation.medical_json = dossier

        await self.session.flush()
        await self.session.commit()

    async def record_decision(
        self,
        consultation_id: uuid.UUID,
        *,
        item_key: str,
        decision: str,
        note: Optional[str],
        doctor_id: uuid.UUID,
        doctor_name: str,
    ) -> Optional[Dict[str, Any]]:

        # Also eagerly load relationships here for consistency
        consultation = await self.consultations.get_with_details(
            consultation_id
        )

        if consultation is None:
            return None

        dossier = dict(consultation.medical_json or {})

        copilot = dict(
            dossier.get("copilot") or {}
        )

        decisions = dict(
            copilot.get("decisions") or {}
        )

        decisions[item_key] = {
            "decision": decision,
            "note": note,
            "doctor_id": str(doctor_id),
            "doctor_name": doctor_name,
            "at": datetime.now(timezone.utc).isoformat(),
        }

        copilot["decisions"] = decisions
        dossier["copilot"] = copilot
        consultation.medical_json = dossier

        await self.session.flush()
        await self.session.commit()

        logger.info(
            "copilot_decision",
            extra={
                "consultation_id": str(consultation_id),
                "item": item_key,
                "decision": decision,
                "doctor": doctor_name,
            },
        )

        return decisions[item_key]