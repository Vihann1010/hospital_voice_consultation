#!/usr/bin/env python3
"""Assign UHIDs to patients that do not have one.

    python -m scripts.backfill_uhids --dry-run
    python -m scripts.backfill_uhids

Needed once after upgrading an existing installation, and again after
importing records from a previous system.

Deliberately a separate, explicit script rather than part of the migration:
it writes identifiers that get printed on paperwork and read back over a
counter, so it should be run knowingly and its output kept.

Ordering is by creation date, so the hospital's earliest patients receive the
earliest numbers — which is what staff expect when they look one up.
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

sys.path.insert(0, ".")

from app.billing.identifiers import build_uhid  # noqa: E402
# Importing the registry defines every mapper before any model is used.
# Without it SQLAlchemy cannot resolve relationships declared by string
# name (Patient -> "Consultation"), and the script dies on first use.
from app.models import registry as _registry  # noqa: F401,E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.emr import DocumentCounter  # noqa: E402
from app.models.patient import Patient  # noqa: E402


async def backfill(dry_run: bool) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Patient)
            .where(Patient.uhid.is_(None))
            .order_by(Patient.created_at)
        )
        patients = list(result.scalars().all())
        if not patients:
            print("Every patient already has a UHID. Nothing to do.")
            return

        counter_result = await session.execute(
            select(DocumentCounter).where(
                DocumentCounter.scope == "uhid", DocumentCounter.period == "all"
            )
        )
        counter = counter_result.scalar_one_or_none()
        if counter is None:
            counter = DocumentCounter(scope="uhid", period="all", last_value=0)
            session.add(counter)
            await session.flush()

        start = counter.last_value
        print(f"{len(patients)} patient(s) without a UHID; continuing from {start}.")

        for offset, patient in enumerate(patients, start=1):
            uhid = build_uhid(start + offset, patient.created_at.date())
            if dry_run:
                print(f"  would assign {uhid}  {patient.name}")
            else:
                patient.uhid = uhid

        if dry_run:
            print("\nDry run — nothing written. Re-run without --dry-run to apply.")
            return

        counter.last_value = start + len(patients)
        await session.commit()
        print(f"Assigned {len(patients)} UHID(s). Counter now at {counter.last_value}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assign missing UHIDs.")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be assigned, write nothing")
    args = parser.parse_args()
    asyncio.run(backfill(args.dry_run))
