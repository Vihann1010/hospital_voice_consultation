#!/usr/bin/env python3
"""Rebuild an intake's record and summary from its saved conversation.

    python -m scripts.refinalize_intake <consultation-id> [<consultation-id> ...]

For an intake whose conversation was saved but whose summary was lost, e.g.
to a fault in the pipeline at the end of the call. The conversation is
re-read from the database and put through the same pipeline a live call ends
with. Vitals already recorded against the consultation are kept. Nothing is
spoken to anyone and the consultation's status is left as it is.
"""
import asyncio
import sys
import uuid

sys.path.insert(0, ".")

from app.models import registry as _registry  # noqa: F401,E402
from app.ai.pipeline.pipeline import clinical_pipeline  # noqa: E402
from app.ai.session.memory import ConversationMemory  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.enums import TurnRole  # noqa: E402
from app.models.patient import Patient  # noqa: E402
from app.services.consultant_directory import department_doctor_name  # noqa: E402
from app.services.consultation_service import ConsultationService  # noqa: E402


async def refinalize(consultation_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        service = ConsultationService(session)
        consultation = await service.consultations.get(consultation_id)
        if consultation is None:
            print(f"{consultation_id}: not found")
            return
        # Loaded explicitly: an async session cannot lazy-load the relationship.
        patient = await session.get(Patient, consultation.patient_id)
        turns = await service.consultations.get_turns(consultation_id)
        if not turns:
            print(f"{consultation_id}: no conversation saved; nothing to rebuild from")
            return

        memory = ConversationMemory(
            consultation_id=consultation.id,
            department=consultation.department,
            patient_info={
                "name": patient.name,
                "age": patient.age,
                "gender": patient.gender.value,
                "phone_number": patient.phone_number,
            },
            doctor_name=await department_doctor_name(session, consultation.department),
        )
        for turn in turns:
            if turn.role == TurnRole.PATIENT:
                memory.add_patient_turn(turn.content)
            else:
                memory.add_assistant_turn(turn.content, interrupted=turn.interrupted)

        dossier = (await clinical_pipeline.finalize(memory)).model_dump()
        existing = consultation.medical_json or {}
        if existing.get("vitals") and "vitals" not in dossier:
            dossier["vitals"] = existing["vitals"]
        consultation.medical_json = dossier
        await session.commit()

        errors = dossier.get("pipeline_errors") or []
        record = dossier.get("medical_json") or {}
        print(f"{consultation_id}: rebuilt from {len(turns)} turns; "
              f"chief complaint: {record.get('chief_complaint')!r}; "
              f"{len(errors)} stage error(s)")
        for error in errors:
            print(f"    {error}")


async def main(ids) -> None:
    for raw in ids:
        await refinalize(uuid.UUID(raw))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
