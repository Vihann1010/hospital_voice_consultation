#!/usr/bin/env python3
"""Seed Satya Hospital's wards and beds.

    python -m scripts.seed_wards

Idempotent: an existing ward code is repriced and missing beds are added, so
this can be re-run after editing the layout below.

**These are placeholder rates and a placeholder bed count.** Set the
hospital's real tariff and real ward layout before admitting anybody.
"""
import asyncio
import sys

from sqlalchemy import select

sys.path.insert(0, ".")

from app.models import registry as _registry  # noqa: F401,E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.enums import Department, WardType  # noqa: E402
from app.models.ipd import Bed, Ward  # noqa: E402

ORTHO = Department.ORTHOPEDICS
GYN = Department.GYNECOLOGY

# (code, name, type, department, beds, prefix, bed ₹/day, nursing ₹/day, oxygen)
LAYOUT = [
    ("GW-M", "General Ward — Male", WardType.GENERAL, ORTHO, 12, "GM", 1500, 300, False),
    ("GW-F", "General Ward — Female", WardType.GENERAL, GYN, 12, "GF", 1500, 300, False),
    ("SP", "Semi-Private", WardType.SEMI_PRIVATE, None, 8, "SP", 3000, 500, False),
    ("PR", "Private Rooms", WardType.PRIVATE, None, 6, "PR", 5000, 800, True),
    ("DLX", "Deluxe Rooms", WardType.DELUXE, None, 2, "DX", 8000, 1000, True),
    ("ICU", "Intensive Care", WardType.ICU, None, 6, "IC", 12000, 2500, True),
    ("HDU", "High Dependency", WardType.HDU, None, 4, "HD", 8000, 1800, True),
    ("LR", "Labour Room", WardType.LABOUR, GYN, 4, "LR", 4000, 1000, True),
    ("POW", "Post-Operative", WardType.POST_OPERATIVE, None, 6, "PO", 4000, 1000, True),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        wards_created = wards_updated = beds_created = 0

        for code, name, ward_type, department, count, prefix, rate, nursing, oxygen in LAYOUT:
            result = await session.execute(select(Ward).where(Ward.code == code))
            ward = result.scalar_one_or_none()

            if ward is None:
                ward = Ward(
                    code=code, name=name, ward_type=ward_type, department=department,
                    daily_rate_paise=rate * 100, nursing_rate_paise=nursing * 100,
                    is_active=True,
                )
                session.add(ward)
                await session.flush()
                wards_created += 1
            else:
                ward.name = name
                ward.ward_type = ward_type
                ward.department = department
                ward.daily_rate_paise = rate * 100
                ward.nursing_rate_paise = nursing * 100
                wards_updated += 1

            existing = await session.execute(select(Bed.label).where(Bed.ward_id == ward.id))
            have = {label for (label,) in existing.all()}
            for number in range(1, count + 1):
                label = f"{prefix}-{number:02d}"
                if label not in have:
                    session.add(Bed(ward_id=ward.id, label=label,
                                    is_oxygen_supported=oxygen))
                    beds_created += 1

        await session.commit()
        total = await session.execute(select(Bed))
        print(f"Wards: {wards_created} created, {wards_updated} repriced. "
              f"Beds: {beds_created} added, {len(list(total.scalars().all()))} total.")
        print("These are placeholder rates — set the hospital's own before go-live.")


if __name__ == "__main__":
    asyncio.run(seed())
