"""Who the patient is being prepared for.

The intake assistant and the pre-consultation summary both name the doctor.
That name used to be written into the prompts, which meant two things: a third
department was told it was seeing the gynaecologist, and the day a consultant
left, their name kept being spoken to patients until someone edited Python.

The hospital already maintains this in the consultant register, so that is
where it is read from. A department with no consultant — or with several, where
picking one would be a guess — resolves to None and the prompts say "the
doctor", which is the honest thing to say when the software does not know.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultant import Consultant
from app.models.enums import Department


async def department_doctor_name(
    session: AsyncSession, department: Department
) -> Optional[str]:
    """The name of the one active consultant in this department, if there is one."""
    result = await session.execute(
        select(Consultant.full_name)
        .where(
            Consultant.department == department,
            Consultant.is_active.is_(True),
        )
        # Two is enough to know it is not one; no point loading a whole clinic.
        .limit(2)
    )
    names = result.scalars().all()
    return names[0] if len(names) == 1 else None
