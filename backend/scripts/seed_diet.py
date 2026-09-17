"""Load a starting diet list. Safe to re-run: existing diets are left as they are.

    docker exec satya-backend python scripts/seed_diet.py

These are the diets most wards order by name. The kitchen and the dietitian
decide what each means on the plate; rename, describe or retire them in
Settings -> Diet list.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import registry  # noqa: E402,F401
from app.models.diet import DietMode  # noqa: E402

DIETS = [
    ("NORMAL", "Normal diet", False),
    ("SOFT", "Soft diet", False),
    ("SEMISOLID", "Semi-solid diet", False),
    ("LIQUID", "Liquid diet", False),
    ("CLEARLIQ", "Clear liquid diet", False),
    ("DIABETIC", "Diabetic diet", False),
    ("LOWSALT", "Low salt diet", False),
    ("RENAL", "Renal diet", False),
    ("HIPROT", "High protein diet", False),
    ("RT", "Ryle's tube feed", False),
    ("NBM", "Nil by mouth", True),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        present = {mode.code for mode in (await session.execute(select(DietMode))).scalars()}
        added = 0
        for position, (code, name, nbm) in enumerate(DIETS):
            if code in present:
                continue
            session.add(DietMode(code=code, name=name, is_nil_by_mouth=nbm, position=position * 10))
            added += 1
        await session.commit()
        print(f"diet list: {added} added, {len(present)} already present")


if __name__ == "__main__":
    asyncio.run(seed())
