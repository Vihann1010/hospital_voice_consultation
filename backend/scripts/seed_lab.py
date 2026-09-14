"""Load the starter laboratory: the short lists and the test list.

Safe to re-run. Entries that already exist are left exactly as they are, so a
pathologist's edits are never overwritten by a second run.

    docker exec satya-backend python scripts/seed_lab.py

Every test is loaded unreviewed. See app/lab/defaults.py for why.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.lab import defaults  # noqa: E402
from app.models import registry  # noqa: E402,F401
from app.models.emr import ServiceItem  # noqa: E402
from app.models.lab import LabMaster, LabParameter, LabTest  # noqa: E402


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        present = {(master.kind, master.name.lower()) for master in (await session.execute(select(LabMaster))).scalars()}
        added = 0
        lists = [("group", defaults.GROUPS), ("unit", defaults.UNITS), ("specimen", defaults.SPECIMENS),
                 ("method", defaults.METHODS), ("organism", defaults.ORGANISMS)]
        for kind, names in lists:
            for position, name in enumerate(names):
                if (kind, name.lower()) not in present:
                    session.add(LabMaster(kind=kind, name=name, position=position))
                    added += 1
        for position, (name, category) in enumerate(defaults.ANTIBIOTICS):
            if ("antibiotic", name.lower()) not in present:
                session.add(LabMaster(kind="antibiotic", name=name, category=category, position=position))
                added += 1

        codes = set((await session.execute(select(LabTest.code))).scalars())
        prices = set((await session.execute(select(ServiceItem.code))).scalars())
        tests = 0
        unpriced = []
        for position, (code, name, group, specimen, catalog_code, service_code, parameters, culture,
                       turnaround) in enumerate(defaults.TESTS):
            if code in codes:
                continue
            test = LabTest(
                code=code, name=name, group_name=group, specimen=specimen, catalog_code=catalog_code,
                service_code=service_code if service_code in prices else None, is_culture=culture,
                turnaround_hours=turnaround, position=position, is_active=True,
            )
            test.parameters = [
                LabParameter(
                    position=index, name=entry["name"], analyte_key=entry.get("analyte_key"), aliases=[],
                    result_type=entry["result_type"], unit=entry.get("unit") or None, method=None,
                    choices=entry.get("choices", []), normal_values=entry.get("normal_values", []),
                    ranges=entry.get("ranges", []), range_text=None,
                    print_default=entry.get("print_default", True), is_active=True,
                )
                for index, entry in enumerate(parameters)
            ]
            session.add(test)
            tests += 1
            if test.service_code is None:
                unpriced.append(code)
        await session.commit()
        print(f"lab list entries added: {added}")
        print(f"lab tests added: {tests} (all unreviewed)")
        if unpriced:
            print(f"tests with no price code yet: {', '.join(unpriced)}")


if __name__ == "__main__":
    asyncio.run(seed())
