#!/usr/bin/env python3
"""Seed Smile Dental: tariff, dental chair, procedure list.

    python -m scripts.seed_smile_dental

The dental practice inside the same clinic as CN Gastrocare. Idempotent, like
scripts/seed_gastro_clinic.py: an existing code is updated, not duplicated.

**Every rate here is a placeholder**, there so the counter can bill a dental
patient on day one. Set Smile Dental's own before go-live.

Not created here, on purpose: the dentist's consultant entry and login (hers
to enter, and the intake assistant reads the name it speaks from that
register), and anything from an outside dental laboratory (crowns and
dentures are priced here as the whole job; the lab's invoice is the clinic's
expense, not a line on the patient's bill).
"""
import asyncio
import sys

from sqlalchemy import select

sys.path.insert(0, ".")

from app.models import registry as _registry  # noqa: F401,E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.emr import ServiceItem  # noqa: E402
from app.models.enums import Department, ServiceCategory  # noqa: E402
from app.models.theatre import Operation, TheatreRoom  # noqa: E402

DENTAL = Department.DENTISTRY
PROC = ServiceCategory.PROCEDURE
INV = ServiceCategory.INVESTIGATION

# (code, name, category, rupees). Clinical services are GST-exempt (Notification
# 12/2017 Central Tax (Rate)), so tax is 0. Cosmetic work (whitening, veneers)
# is not exempt and is deliberately not listed: price it with the tax on.
TARIFF = [
    ("OPD-DEN-NEW", "OPD consultation — Dentistry (new)", ServiceCategory.CONSULTATION, 300),
    ("OPD-DEN-FUP", "OPD consultation — Dentistry (follow-up)", ServiceCategory.CONSULTATION, 200),

    ("DEN-SCALING", "Scaling and polishing (full mouth)", PROC, 1000),
    ("DEN-FILL-GIC", "Filling — glass ionomer (per tooth)", PROC, 800),
    ("DEN-FILL-COMP", "Filling — composite (per tooth)", PROC, 1500),
    ("DEN-RCT-ANT", "Root canal treatment — front tooth", PROC, 3500),
    ("DEN-RCT-POST", "Root canal treatment — back tooth", PROC, 5000),
    ("DEN-PULPECTOMY", "Pulpectomy — milk tooth", PROC, 2500),
    ("DEN-POST-CORE", "Post and core build-up (per tooth)", PROC, 1500),
    ("DEN-EXT", "Extraction — simple (per tooth)", PROC, 800),
    ("DEN-EXT-SURG", "Extraction — surgical or impacted tooth", PROC, 3000),
    ("DEN-CROWN-PFM", "Crown — porcelain fused to metal (per tooth)", PROC, 5000),
    ("DEN-CROWN-ZIRC", "Crown — zirconia (per tooth)", PROC, 10000),
    ("DEN-DENTURE-CD", "Complete denture (per arch)", PROC, 12000),
    ("DEN-DRESSING", "Emergency dressing or drainage", PROC, 500),

    ("DEN-IOPA", "Dental X-ray — IOPA / RVG (per film)", INV, 200),
    ("DEN-OPG", "Dental X-ray — OPG", INV, 500),
]

ROOMS = [("CHAIR-1", "Dental chair")]

# (code, name, minutes, price code). Priced per tooth where the tariff is.
OPERATIONS = [
    ("DEN-SCALING", "Scaling and polishing", 30, "DEN-SCALING"),
    ("DEN-FILL-GIC", "Filling — glass ionomer", 20, "DEN-FILL-GIC"),
    ("DEN-FILL-COMP", "Filling — composite", 30, "DEN-FILL-COMP"),
    ("DEN-RCT-ANT", "Root canal treatment — front tooth", 45, "DEN-RCT-ANT"),
    ("DEN-RCT-POST", "Root canal treatment — back tooth", 60, "DEN-RCT-POST"),
    ("DEN-PULPECTOMY", "Pulpectomy — milk tooth", 30, "DEN-PULPECTOMY"),
    ("DEN-EXT", "Extraction — simple", 20, "DEN-EXT"),
    ("DEN-EXT-SURG", "Extraction — surgical or impacted", 45, "DEN-EXT-SURG"),
    ("DEN-CROWN-PREP", "Crown preparation and impression", 45, "DEN-CROWN-PFM"),
    ("DEN-DRESSING", "Emergency dressing or drainage", 15, "DEN-DRESSING"),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        tariff_new = tariff_updated = 0
        for code, name, category, rupees in TARIFF:
            item = (
                await session.execute(select(ServiceItem).where(ServiceItem.code == code))
            ).scalar_one_or_none()
            if item is None:
                session.add(ServiceItem(
                    code=code, name=name, category=category, department=DENTAL,
                    rate_paise=rupees * 100, tax_percent=0, is_active=True,
                ))
                tariff_new += 1
            else:
                item.name, item.category, item.department = name, category, DENTAL
                item.rate_paise, item.tax_percent = rupees * 100, 0
                tariff_updated += 1

        rooms_new = 0
        for code, name in ROOMS:
            room = (
                await session.execute(select(TheatreRoom).where(TheatreRoom.code == code))
            ).scalar_one_or_none()
            if room is None:
                session.add(TheatreRoom(code=code, name=name, is_active=True))
                rooms_new += 1
            else:
                room.name = name

        ops_new = 0
        for code, name, minutes, service_code in OPERATIONS:
            operation = (
                await session.execute(select(Operation).where(Operation.code == code))
            ).scalar_one_or_none()
            if operation is None:
                session.add(Operation(
                    code=code, name=name, department=DENTAL, default_minutes=minutes,
                    service_code=service_code, is_active=True,
                ))
                ops_new += 1
            else:
                operation.name, operation.department = name, DENTAL
                operation.default_minutes, operation.service_code = minutes, service_code

        await session.commit()

    print(f"Tariff:     {tariff_new} created, {tariff_updated} repriced.")
    print(f"Rooms:      {rooms_new} created.")
    print(f"Procedures: {ops_new} created.")
    print()
    print("Every rate above is a placeholder. Set Smile Dental's own at")
    print("Settings -> Price list before seeing a paying patient.")
    print()
    print("Still to do by hand:")
    print("  * Settings -> Consultants — the dentist, her OPD hours, fee and")
    print("    registration number.")
    print("  * Settings -> Staff accounts — her login.")
    print("  * The dental formulary is withheld until she has reviewed it; add")
    print("    dentistry to APPROVED_FORMULARY then.")


if __name__ == "__main__":
    asyncio.run(seed())
