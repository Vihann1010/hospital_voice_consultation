"""Security primitives: password hashing and JWT issuance/verification."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_CONSULTATION = "consultation"
TOKEN_TYPE_FINANCE_UNLOCK = "finance_unlock"


# bcrypt hashes only the first 72 bytes of a password and silently ignores the
# rest. Left unchecked, a 100-character passphrase and its first 72 characters
# are interchangeable at login — two different secrets that open the same
# account. Rejecting at the boundary is clearer than truncating quietly.
BCRYPT_MAX_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised rather than letting bcrypt discard the end of a password."""


def hash_password(password: str) -> str:
    encoded = (password or "").encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise PasswordTooLongError(
            f"A password may be at most {BCRYPT_MAX_BYTES} bytes "
            f"(about {BCRYPT_MAX_BYTES} characters, fewer if it contains "
            "non-English letters). Please choose a shorter one."
        )
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    # An over-long password can never have been set through hash_password, so
    # it cannot be correct — and comparing it would compare only its first 72
    # bytes, which is the failure this guards against.
    if len((plain or "").encode("utf-8")) > BCRYPT_MAX_BYTES:
        return False
    return pwd_context.verify(plain, hashed)


def _encode(claims: Dict[str, Any], expires_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    claims = {**claims, "iat": now, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(*, user_id: UUID, role: str) -> str:
    return _encode(
        {"sub": str(user_id), "role": role, "type": TOKEN_TYPE_ACCESS},
        settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )


def create_consultation_token(*, consultation_id: UUID, patient_id: UUID) -> str:
    """Short-lived token that authorizes a single patient voice session."""
    return _encode(
        {
            "sub": str(patient_id),
            "consultation_id": str(consultation_id),
            "role": "patient",
            "type": TOKEN_TYPE_CONSULTATION,
        },
        settings.CONSULTATION_TOKEN_EXPIRE_MINUTES,
    )


def create_finance_unlock_token(*, user_id: UUID, role: str) -> str:
    return _encode(
        {"sub": str(user_id), "role": role, "type": TOKEN_TYPE_FINANCE_UNLOCK},
        30,
    )


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
