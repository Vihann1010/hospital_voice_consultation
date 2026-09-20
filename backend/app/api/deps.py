"""Dependency injection wiring: sessions, services, current user, RBAC."""
import uuid
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import bind_user
from app.core.permissions import Permission, has_permission
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import get_db
from app.models.user import User
from app.modules import Module
from app.repositories.user_repository import UserRepository
from app.services.appointment_service import AppointmentService
from app.services.auth_service import AuthService
from app.services.consultation_service import ConsultationService
from app.services.diary_service import DiaryService
from app.services.copilot_service import CopilotService
from app.services.investigation_service import InvestigationService
from app.services.pad_service import PadService
from app.services.prescription_service import PrescriptionService
from app.services.ipd_service import IPDService
from app.services.reception_service import ReceptionService
from app.services.patient_service import PatientService

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_auth_service(session: DbSession) -> AuthService:
    return AuthService(session)


def get_appointment_service(session: DbSession) -> AppointmentService:
    return AppointmentService(session)


def get_diary_service(session: DbSession) -> DiaryService:
    return DiaryService(session)


def get_consultation_service(session: DbSession) -> ConsultationService:
    return ConsultationService(session)


def get_patient_service(session: DbSession) -> PatientService:
    return PatientService(session)


def get_copilot_service(session: DbSession) -> CopilotService:
    return CopilotService(session)


def get_investigation_service(session: DbSession) -> InvestigationService:
    return InvestigationService(session)


def get_prescription_service(session: DbSession) -> PrescriptionService:
    return PrescriptionService(session)


def get_reception_service(session: DbSession) -> ReceptionService:
    return ReceptionService(session)


def get_ipd_service(session: DbSession) -> IPDService:
    return IPDService(session)


async def get_current_user(
    request: Request,
    session: DbSession,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    claims = decode_token(credentials.credentials)
    if claims is None or claims.get("type") != TOKEN_TYPE_ACCESS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject")
    user = await UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    # Who made this request: on request.state for the request log line, and in
    # the log context so every line a service writes names the user.
    request.state.user_id = str(user.id)
    request.state.user_role = user.role.value
    bind_user(user.id, user.role.value)
    return user


def get_pad_service(session: DbSession) -> PadService:
    return PadService(session)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_any_permission(*permissions: Permission):
    """Authorisation guard for a screen two different jobs reach.

    `require_permission` demands every named permission; this one accepts any,
    for the few endpoints legitimately read by more than one kind of staff —
    the price list is read at the counter to bill, and by management to price.
    """

    async def checker(user: CurrentUser) -> User:
        if not any(has_permission(user.role, p) for p in permissions):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires one of: {', '.join(p.value for p in permissions)}",
            )
        return user

    return checker


def require_module(module: Module):
    """Refuse an endpoint that belongs to a module this installation does not run.

    Most module endpoints are never registered at all (see app/api/v1/router.py),
    which is the stronger switch. This is for the few that live inside another
    module's router — the room-charge run sits with the ward — where the choice
    is between one dependency and splitting a router to make a point.
    """

    async def checker() -> None:
        if not settings.module_enabled(module):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"The {module.value.replace('_', ' ')} module is not enabled here.",
            )

    return checker


def require_permission(*permissions: Permission):
    """Authorisation guard, e.g. Depends(require_permission(Permission.REFUND_ISSUE)).

    Routes name the permission they need, never the roles that happen to hold
    it. The catalogue in app.core.permissions is the only place the mapping
    lives, and it is the same thing /auth/me/permissions reports to the front
    end — so the buttons a user is shown and the calls the API will accept
    cannot drift apart, and adding a role does not mean revisiting every route.

    All named permissions are required, not any of them.
    """

    async def checker(user: CurrentUser) -> User:
        missing = [p for p in permissions if not has_permission(user.role, p)]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires permission: {', '.join(p.value for p in missing)}",
            )
        return user

    return checker
