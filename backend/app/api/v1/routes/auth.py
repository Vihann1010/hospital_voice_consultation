from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser, get_auth_service
from app.core.audit import client_ip, record as audit_record
from app.core.permissions import permissions_for
from app.models.enums import AuditAction
from app.schemas.schemas import LoginRequest, TokenResponse, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Staff sign-in.

    Both outcomes are audited: successful logins for accountability, failures
    because a burst of them from one address is how credential stuffing looks.
    The error message is identical either way, so it cannot be used to discover
    which email addresses exist.
    """
    token = await auth.authenticate(payload.email, payload.password)
    context = {
        "ip_address": client_ip(request),
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }

    if token is None:
        await audit_record(
            AuditAction.LOGIN_FAILURE,
            actor_name=payload.email[:255],
            success=False,
            detail={"reason": "invalid_credentials"},
            **context,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    user = await auth.users.get_by_email(payload.email)
    await audit_record(
        AuditAction.LOGIN_SUCCESS,
        actor_id=user.id if user else None,
        actor_name=user.full_name if user else payload.email,
        actor_role=user.role.value if user else None,
        **context,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/me/permissions")
async def my_permissions(user: CurrentUser) -> dict:
    """What this account is allowed to do — drives the front end's affordances."""
    return {
        "role": user.role.value,
        "department": user.department.value if user.department else None,
        "permissions": sorted(permission.value for permission in permissions_for(user.role)),
    }
