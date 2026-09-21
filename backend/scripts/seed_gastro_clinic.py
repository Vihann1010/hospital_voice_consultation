#!/usr/bin/env python3
"""Seed a gastroenterology clinic: tariff, procedure room, procedure list.

    python -m scripts.seed_gastro_clinic

Idempotent: an existing code is updated, not duplicated, so this can be re-run
after editing the lists below.

**Every rate here is a placeholder.** They exist so a fresh install has a
working counter on day one rather than an empty tariff and a receptionist who
cannot bill anybody. Set the clinic's own before go-live.

What this does NOT create, on purpose:

* **Staff logins.** One administrator is seeded on first boot; every other
  account is made from Settings → Staff accounts, which records who created it.
* **Consultants.** The endoscopist's name, OPD hours, fee and registration
  number are the clinic's to enter, and the intake assistant reads the name it
  speaks to patients from that register. A name seeded here would be a
  placeholder said out loud to a patient.
* **Wards, beds or diet.** This clinic has no beds; those modules are off.
"""
import asyncio
import sys

from sqlalchemy import select

sys.path.insert(0, ".")

# Importing the registry defines every mapper before any model is used.
from app.models import registry as _registry  # noqa: F401,E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.emr import ServiceItem  # noqa: E402
from app.models.enums import Department, ServiceCategory  # noqa: E402
from app.models.theatre import Operation, TheatreRoom  # noqa: E402

GASTRO = Department.GASTROENTEROLOGY

# (code, name, category, department, rupees, tax %)
# Clinical services are GST-exempt under Notification 12/2017 Central Tax
# (Rate), so tax is 0 throughout.
TARIFF = [
    ("REG-NEW", "New patient registration", ServiceCategory.REGISTRATION, None, 100, 0),
    ("REG-REP", "Repeat registration (valid 1 year)", ServiceCategory.REGISTRATION, None, 50, 0),

    ("OPD-GAS-NEW", "OPD consultation — Gastroenterology (new)",
     ServiceCategory.CONSULTATION, GASTRO, 600, 0),
    ("OPD-GAS-FUP", "OPD consultation — Gastroenterology (follow-up)",
     ServiceCategory.CONSULTATION, GASTRO, 300, 0),

    # The procedures. Priced as the whole episode — the room, the endoscopist
    # and the sedation — because that is what the counter quotes and what the
    # patient is asked to pay.
    ("PROC-OGD", "Upper GI endoscopy (gastroscopy)", ServiceCategory.PROCEDURE, GASTRO, 2500, 0),
    ("PROC-OGD-BIOPSY", "Upper GI endoscopy with biopsy",
     ServiceCategory.PROCEDURE, GASTRO, 3500, 0),
    ("PROC-COLON", "Colonoscopy", ServiceCategory.PROCEDURE, GASTRO, 5000, 0),
    ("PROC-COLON-BIOPSY", "Colonoscopy with biopsy",
     ServiceCategory.PROCEDURE, GASTRO, 6500, 0),
    ("PROC-SIGMOID", "Flexible sigmoidoscopy", ServiceCategory.PROCEDURE, GASTRO, 3000, 0),
    # Charged separately because it is not always given, and a patient who
    # declines sedation should not be billed for it.
    ("PROC-SEDATION", "Conscious sedation for a day procedure",
     ServiceCategory.PROCEDURE, GASTRO, 1200, 0),
    # The specimen leaves the building; this is the clinic's handling charge
    # plus what the outside laboratory bills.
    ("PROC-HPE", "Histopathology of endoscopic biopsy (outside laboratory)",
     ServiceCategory.INVESTIGATION, GASTRO, 1500, 0),

    ("INV-UBT", "H. pylori urea breath test", ServiceCategory.INVESTIGATION, GASTRO, 2000, 0),
    ("INV-USG-ABDO", "Ultrasound whole abdomen", ServiceCategory.INVESTIGATION, None, 1200, 0),
    ("INV-ELASTO", "Liver elastography (FibroScan)",
     ServiceCategory.INVESTIGATION, GASTRO, 3000, 0),
]

# (code, name, room)
ROOMS = [
    ("ENDO", "Endoscopy suite"),
    # Where the patient lies down for the half hour after sedation. A clinic
    # that sends people home needs somewhere to keep them until they are fit
    # to go, and it is a room the list books like any other.
    ("RECOVERY", "Recovery bay"),
]

# (code, name, minutes, price code)
OPERATIONS = [
    ("OGD", "Upper GI endoscopy (gastroscopy)", 15, "PROC-OGD"),
    ("OGD-BX", "Upper GI endoscopy with biopsy", 20, "PROC-OGD-BIOPSY"),
    ("COLON", "Colonoscopy", 30, "PROC-COLON"),
    ("COLON-BX", "Colonoscopy with biopsy", 40, "PROC-COLON-BIOPSY"),
    ("SIGMOID", "Flexible sigmoidoscopy", 20, "PROC-SIGMOID"),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        tariff_new = tariff_updated = 0
        for code, name, category, department, rupees, tax in TARIFF:
            item = (
                await session.execute(select(ServiceItem).where(ServiceItem.code == code))
            ).scalar_one_or_none()
            if item is None:
                session.add(ServiceItem(
                    code=code, name=name, category=category, department=department,
                    rate_paise=rupees * 100, tax_percent=tax, is_active=True,
                ))
                tariff_new += 1
            else:
                item.name, item.category, item.department = name, category, department
                item.rate_paise, item.tax_percent = rupees * 100, tax
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
                    code=code, name=name, department=GASTRO, default_minutes=minutes,
                    service_code=service_code, is_active=True,
                ))
                ops_new += 1
            else:
                operation.name = name
                operation.department = GASTRO
                operation.default_minutes = minutes
                operation.service_code = service_code

        await session.commit()

    print(f"Tariff:     {tariff_new} created, {tariff_updated} repriced.")
    print(f"Rooms:      {rooms_new} created.")
    print(f"Procedures: {ops_new} created.")
    print()
    print("Every rate above is a placeholder. Set the clinic's own at")
    print("Settings -> Price list before seeing a paying patient.")
    print()
    print("Still to do by hand, because they are the clinic's to decide:")
    print("  * Settings -> Consultants — the endoscopist, their OPD hours, fee")
    print("    and registration number. The intake assistant reads the name it")
    print("    speaks to patients from here.")
    print("  * Settings -> Staff accounts — a login for everyone who needs one.")
    print("  * The gastroenterology formulary is withheld until a specialist")
    print("    has reviewed it; see APPROVED_FORMULARY in docs/DEPLOYMENT.md.")


if __name__ == "__main__":
    asyncio.run(seed())
