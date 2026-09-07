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
    """Idempotently create the admin and the two consulting doctors."""
    users = UserRepository(session)
    defaults = [
        (settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD, "Administrator", UserRole.ADMIN, None),
        (
            settings.DR_AK_AGARWAL_EMAIL,
            settings.DR_AK_AGARWAL_PASSWORD,
            "Dr. A K Agarwal",
            UserRole.DOCTOR,
            Department.ORTHOPEDICS,
        ),
        (
            settings.DR_MANISHA_AGARWAL_EMAIL,
            settings.DR_MANISHA_AGARWAL_PASSWORD,
            "Dr. Manisha Agarwal",
            UserRole.DOCTOR,
            Department.GYNECOLOGY,
        ),
    ]
    for email, password, full_name, role, department in defaults:
        if await users.get_by_email(email) is None:
            await users.add(
                User(
                    email=email.lower(),
                    full_name=full_name,
                    hashed_password=hash_password(password),
                    role=role,
                    department=department,
                )
            )
            logger.info("seeded_user", extra={"email": email, "role": role.value})
    await session.commit()
