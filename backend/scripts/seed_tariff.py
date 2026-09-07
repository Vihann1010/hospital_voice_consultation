#!/usr/bin/env python3
"""Seed the OPD price list.

    python -m scripts.seed_tariff

Idempotent: an existing code is repriced, not duplicated, so this can be
re-run after editing the rates below.

Rates are placeholders — Satya Hospital must set its own before go-live. They
are here so a fresh install has a working reception counter on day one rather
than an empty tariff and a cashier who cannot bill anybody.

Most clinical services are GST-exempt under Notification 12/2017 Central Tax
(Rate), so tax_percent is 0 throughout. Retail items a hospital sells are not
exempt and should carry their actual rate.
"""
import asyncio
import sys

from sqlalchemy import select

sys.path.insert(0, ".")

# Importing the registry defines every mapper before any model is used.
# Without it SQLAlchemy cannot resolve relationships declared by string
# name (Patient -> "Consultation"), and the script dies on first use.
from app.models import registry as _registry  # noqa: F401,E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.emr import ServiceItem  # noqa: E402
from app.models.enums import Department, ServiceCategory  # noqa: E402

ORTHO = Department.ORTHOPEDICS
GYN = Department.GYNECOLOGY

# (code, name, category, department, rupees, tax %)
TARIFF = [
    ("REG-NEW", "New patient registration", ServiceCategory.REGISTRATION, None, 100, 0),
    ("REG-REP", "Repeat registration (valid 1 year)", ServiceCategory.REGISTRATION, None, 50, 0),

    ("OPD-ORT-NEW", "OPD consultation — Orthopedics (new)", ServiceCategory.CONSULTATION, ORTHO, 500, 0),
    ("OPD-ORT-FUP", "OPD consultation — Orthopedics (follow-up)", ServiceCategory.CONSULTATION, ORTHO, 300, 0),
    ("OPD-GYN-NEW", "OPD consultation — Gynecology (new)", ServiceCategory.CONSULTATION, GYN, 500, 0),
    ("OPD-GYN-FUP", "OPD consultation — Gynecology (follow-up)", ServiceCategory.CONSULTATION, GYN, 300, 0),

    ("PRC-DRESS", "Dressing (simple)", ServiceCategory.PROCEDURE, ORTHO, 200, 0),
    ("PRC-DRESS-L", "Dressing (large / burn)", ServiceCategory.PROCEDURE, ORTHO, 500, 0),
    ("PRC-INJ-IM", "Injection — intramuscular", ServiceCategory.PROCEDURE, None, 100, 0),
    ("PRC-INJ-IA", "Injection — intra-articular", ServiceCategory.PROCEDURE, ORTHO, 1500, 0),
    ("PRC-POP", "Plaster / POP application", ServiceCategory.PROCEDURE, ORTHO, 1200, 0),
    ("PRC-POP-REM", "Plaster removal", ServiceCategory.PROCEDURE, ORTHO, 300, 0),
    ("PRC-SUTURE", "Suturing (up to 5 stitches)", ServiceCategory.PROCEDURE, ORTHO, 800, 0),
    ("PRC-SUT-REM", "Suture removal", ServiceCategory.PROCEDURE, ORTHO, 200, 0),
    ("PRC-ASPIR", "Joint aspiration", ServiceCategory.PROCEDURE, ORTHO, 1500, 0),

    ("PRC-ANC", "Antenatal check-up", ServiceCategory.PROCEDURE, GYN, 400, 0),
    ("PRC-PAP", "Pap smear collection", ServiceCategory.PROCEDURE, GYN, 600, 0),
    ("PRC-IUCD", "IUCD insertion", ServiceCategory.PROCEDURE, GYN, 1500, 0),
    ("PRC-IUCD-REM", "IUCD removal", ServiceCategory.PROCEDURE, GYN, 800, 0),

    ("INV-XRAY-1", "X-Ray — single view", ServiceCategory.INVESTIGATION, ORTHO, 350, 0),
    ("INV-XRAY-2", "X-Ray — two views", ServiceCategory.INVESTIGATION, ORTHO, 600, 0),
    ("INV-USG-PELV", "Ultrasound — pelvis", ServiceCategory.INVESTIGATION, GYN, 900, 0),
    ("INV-USG-OBS", "Ultrasound — obstetric", ServiceCategory.INVESTIGATION, GYN, 1100, 0),
    ("INV-CBC", "Complete blood count", ServiceCategory.INVESTIGATION, None, 300, 0),
    ("INV-RBS", "Random blood sugar", ServiceCategory.INVESTIGATION, None, 100, 0),
    ("INV-URINE", "Urine routine", ServiceCategory.INVESTIGATION, None, 200, 0),

    ("OTH-FILE", "Patient file / folder", ServiceCategory.OTHER, None, 30, 0),
    ("OTH-CERT", "Medical certificate", ServiceCategory.OTHER, None, 200, 0),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        created = updated = 0
        for code, name, category, department, rupees, tax in TARIFF:
            result = await session.execute(
                select(ServiceItem).where(ServiceItem.code == code)
            )
            item = result.scalar_one_or_none()
            rate_paise = rupees * 100

            if item is None:
                session.add(
                    ServiceItem(
                        code=code, name=name, category=category, department=department,
                        rate_paise=rate_paise, tax_percent=tax, is_active=True,
                    )
                )
                created += 1
            else:
                item.name = name
                item.category = category
                item.department = department
                item.rate_paise = rate_paise
                item.tax_percent = tax
                updated += 1

        await session.commit()
        print(f"Tariff seeded: {created} created, {updated} repriced.")
        print("These are placeholder rates — set the hospital's own before go-live.")


if __name__ == "__main__":
    asyncio.run(seed())
