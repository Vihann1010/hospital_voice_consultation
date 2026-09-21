"""Authentication + first-boot user seeding."""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.enums import Department, UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.users = UserRepository(session)

    async def authenticate(self, email: str, password: str) -> Optional[str]:
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.hashed_password):
            return None
        return create_access_token(user_id=user.id, role=user.role.value)


async def seed_default_users(session: AsyncSession) -> None:
    """Idempotently create the one account a fresh install needs: the admin.

    This used to seed two named consultants as well — the hospital's own
    orthopaedic surgeon and gynaecologist, written into Python. A different
    clinic installing the same build got two logins for doctors who do not
    work there, each with a shipped default password, and had to be told to
    ignore them.

    Staff belong in the Staff accounts screen, which exists, knows about roles
    and departments, and records who created the account. So the seed creates
    the administrator who will use that screen, and stops. Existing
    deployments are unaffected: this only ever creates what is missing, and
    their accounts are already there.
    """
    users = UserRepository(session)
    if await users.get_by_email(settings.ADMIN_EMAIL) is None:
        await users.add(
            User(
                email=settings.ADMIN_EMAIL.lower(),
                full_name="Administrator",
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                department=None,
            )
        )
        logger.info("seeded_user", extra={"email": settings.ADMIN_EMAIL,
                                          "role": UserRole.ADMIN.value})
    await session.commit()
