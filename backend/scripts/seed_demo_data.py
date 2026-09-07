#!/usr/bin/env python3
"""Seed demonstration data for training and acceptance testing.

Creates patients, completed consultations with realistic dossiers, an
investigation order and a prescription, so a new deployment can be walked
through end to end before real patients are entered.

    python -m scripts.seed_demo_data            # add demo data
    python -m scripts.seed_demo_data --purge    # remove it again

Demo records are tagged with a phone-number prefix so `--purge` can find and
remove exactly what this script created, and nothing else.
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

sys.path.insert(0, ".")

# Importing the registry defines every mapper before any model is used.
# Without it SQLAlchemy cannot resolve relationships declared by string
# name (Patient -> "Consultation"), and the script dies on first use.
from app.models import registry as _registry  # noqa: F401,E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.consultation import Consultation, ConversationTurn  # noqa: E402
from app.models.enums import (  # noqa: E402
    ConsultationStatus, Department, Gender, TurnRole,
)
from app.models.patient import Patient  # noqa: E402

DEMO_PREFIX = "99000"   # demo numbers only; real Indian mobiles never start 99000


DEMO_PATIENTS = [
    {
        "name": "Sunita Verma", "age": 52, "gender": Gender.FEMALE,
        "phone": f"{DEMO_PREFIX}00001", "department": Department.ORTHOPEDICS,
        "complaint": "Pain in both knees for 8 months, worse on stairs",
        "risk": "moderate",
        "dossier_extra": {
            "medical_history": ["Type 2 diabetes (8 years)", "Hypothyroidism"],
            "current_medicines": [
                {"name": "Metformin", "dose_or_frequency": "500 mg twice daily"},
                {"name": "Thyronorm", "dose_or_frequency": "50 mcg once daily"},
            ],
            "allergies": ["Penicillin"],
        },
    },
    {
        "name": "Meera Gupta", "age": 29, "gender": Gender.FEMALE,
        "phone": f"{DEMO_PREFIX}00002", "department": Department.GYNECOLOGY,
        "complaint": "Irregular periods for 10 months with weight gain",
        "risk": "low",
        "dossier_extra": {
            "medical_history": [], "current_medicines": [], "allergies": [],
        },
    },
    {
        "name": "Ramesh Yadav", "age": 63, "gender": Gender.MALE,
        "phone": f"{DEMO_PREFIX}00003", "department": Department.ORTHOPEDICS,
        "complaint": "Lower back pain radiating to the left leg for 3 weeks",
        "risk": "high",
        "dossier_extra": {
            "medical_history": ["Hypertension"],
            "current_medicines": [{"name": "Telma", "dose_or_frequency": "40 mg once daily"}],
            "allergies": [],
        },
    },
]

CONVERSATION = [
    (TurnRole.ASSISTANT, "Namaste! I am the assistant from Satya Hospital. "
                         "Before you see the doctor, may I ask what is troubling you?"),
    (TurnRole.PATIENT, "{complaint}"),
    (TurnRole.ASSISTANT, "I understand. How long has this been going on, and does "
                         "anything make it worse?"),
    (TurnRole.PATIENT, "It has been some months now. Climbing stairs makes it much worse."),
    (TurnRole.ASSISTANT, "Thank you. Are you taking any medicines at the moment?"),
    (TurnRole.PATIENT, "Yes, I take a few tablets regularly for my other conditions."),
    (TurnRole.ASSISTANT, "Noted. The doctor will see you shortly with all of this ready."),
]


def build_dossier(entry: dict) -> dict:
    return {
        "schema_version": "2.0",
        "medical_json": {
            "chief_complaint": entry["complaint"],
            "duration": "several months",
            "symptoms": [{"name": "pain", "details": entry["complaint"]}],
            "red_flags": [],
            **entry["dossier_extra"],
        },
        "risk_assessment": {
            "overall_risk": entry["risk"], "emergency": False, "red_flags": [],
            "triage_priority": "soon" if entry["risk"] == "high" else "routine",
            "recommended_action": "Routine specialist review.",
        },
        "clinical_summary": {
            "one_liner": f"{entry['age']}-year-old "
                         f"{'woman' if entry['gender'] is Gender.FEMALE else 'man'} with "
                         f"{entry['complaint'].lower()}",
            "history_of_present_illness": entry["complaint"],
            "pertinent_positives": [entry["complaint"]],
            "pertinent_negatives": ["No fever", "No recent trauma"],
        },
        "differential_diagnosis": {"differentials": [], "reasoning_note": None},
        "investigations": {"investigations": [], "already_done_to_review": []},
        "patient_education": {"language": "en"},
        "conversation_meta": {"patient_turns": 3, "demo": True},
    }


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        created = 0
        for entry in DEMO_PATIENTS:
            existing = await session.execute(
                select(Patient).where(Patient.phone_number == entry["phone"])
            )
            if existing.scalar_one_or_none() is not None:
                print(f"  · {entry['name']} already present, skipping")
                continue

            patient = Patient(
                name=entry["name"], age=entry["age"], gender=entry["gender"],
                phone_number=entry["phone"],
            )
            session.add(patient)
            await session.flush()

            started = datetime.now(timezone.utc) - timedelta(hours=created + 1)
            consultation = Consultation(
                patient_id=patient.id, department=entry["department"],
                status=ConsultationStatus.COMPLETED,
                medical_json=build_dossier(entry),
                transcript="\n".join(
                    f"{'Patient' if role is TurnRole.PATIENT else 'Satya Assistant'}: "
                    + text.format(complaint=entry["complaint"])
                    for role, text in CONVERSATION
                ),
                started_at=started,
                ended_at=started + timedelta(minutes=6),
            )
            session.add(consultation)
            await session.flush()

            for sequence, (role, text) in enumerate(CONVERSATION):
                session.add(
                    ConversationTurn(
                        consultation_id=consultation.id, role=role,
                        content=text.format(complaint=entry["complaint"]),
                        sequence=sequence, interrupted=False,
                    )
                )
            created += 1
            print(f"  ✓ {entry['name']} — {entry['department'].value}")

        await session.commit()
        print(f"\nSeeded {created} demo patient(s) with consultations.")
        print("Demo records use phone numbers beginning "
              f"{DEMO_PREFIX}; remove them with --purge.")


async def purge() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Patient).where(Patient.phone_number.like(f"{DEMO_PREFIX}%"))
        )
        patients = list(result.scalars().all())
        for patient in patients:
            await session.delete(patient)   # cascades to consultations and turns
        await session.commit()
        print(f"Removed {len(patients)} demo patient(s) and their records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed or purge demonstration data.")
    parser.add_argument("--purge", action="store_true", help="remove demo data")
    arguments = parser.parse_args()
    asyncio.run(purge() if arguments.purge else seed())
