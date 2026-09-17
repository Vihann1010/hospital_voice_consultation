"""Staff accounts: who works here and what they are allowed to do.

Roles are defined in code, not in the database, and this screen assigns them.
That is deliberate. Every route names the permission it requires, so a role is
only meaningful if the permissions in it exist — letting an administrator
invent a role at runtime would let them create one that grants nothing, or
quietly widen one that guards money. Assignment is the safe half of the
problem and the half the hospital actually needs daily.

What the catalogue cannot protect against is an administrator locking the
hospital out of its own system, so the two ways that happens are blocked here:
removing your own administrative access, and removing the last one that exists.
"""
import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.permissions import Permission, ROLE_PERMISSIONS, permissions_for
from app.core.security import hash_password
from app.models.enums import AuditAction, Department, UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.schemas import UserOut

router = APIRouter(prefix="/users", tags=["users"])

ADMINISTER = require_permission(Permission.SYSTEM_ADMIN)

# What each role is for, in the words the hospital uses. Kept beside the
# permission catalogue so the screen can explain a role before it is assigned
# rather than listing permission strings at whoever is creating the account.
ROLE_SUMMARY: Dict[UserRole, str] = {
    UserRole.ADMIN: "Full access, including staff accounts and system settings.",
    UserRole.MANAGER: "Revenue, the price list and the audit trail. No till, no clinical records.",
    UserRole.DOCTOR: "Consults, prescribes, orders and signs off. Cannot reprice or refund.",
    UserRole.SUPERVISOR: "Everything reception does, plus refunds and bill cancellations.",
    UserRole.RECEPTION: "Registers patients, bills, collects payment and reprints bills.",
    UserRole.NURSE: "Charts observations and doses; writes and signs nursing notes. No prescribing.",
    UserRole.LAB: "Registers lab samples and enters results. Verification is the pathologist's.",
}


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    # Only meaningful for doctors, whose records are scoped to their department.
    department: Optional[Department] = None


class UserUpdateRequest(BaseModel):
    # Refused rather than ignored. Sending {"password": "..."} here returned
    # 200 and changed nothing, so an administrator could believe they had
    # reset somebody's password when they had not. Passwords are set through
    # POST /users/{id}/password, which audits the reset.
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    role: Optional[UserRole] = None
    department: Optional[Department] = None
    is_active: Optional[bool] = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: UserRole
    summary: str
    permissions: List[str]
    user_count: int


async def _active_admin_count(session: DbSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    )
    return int(result.scalar_one())


@router.get("/roles", response_model=List[RoleOut], dependencies=[Depends(ADMINISTER)])
async def list_roles(session: DbSession) -> List[RoleOut]:
    """The roles that can be assigned, what each one means, and who holds it."""
    counts = dict(
        (row[0], int(row[1]))
        for row in (
            await session.execute(select(User.role, func.count()).group_by(User.role))
        ).all()
    )
    return [
        RoleOut(
            role=role,
            summary=ROLE_SUMMARY[role],
            permissions=sorted(p.value for p in permissions_for(role)),
            user_count=counts.get(role, 0),
        )
        for role in ROLE_PERMISSIONS
    ]


@router.get("", response_model=List[UserOut], dependencies=[Depends(ADMINISTER)])
async def list_users(
    session: DbSession,
    role: Optional[UserRole] = Query(default=None),
    include_inactive: bool = Query(default=True),
) -> List[UserOut]:
    statement = select(User).order_by(User.role, User.full_name)
    if role is not None:
        statement = statement.where(User.role == role)
    if not include_inactive:
        statement = statement.where(User.is_active.is_(True))
    result = await session.execute(statement)
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(ADMINISTER)])
async def create_user(
    payload: UserCreateRequest, session: DbSession, user: CurrentUser, request: Request
) -> UserOut:
    users = UserRepository(session)
    if await users.get_by_email(payload.email) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An account already exists for that email address.",
        )

    created = await users.add(
        User(
            email=payload.email.lower(),
            full_name=payload.full_name.strip(),
            hashed_password=hash_password(payload.password),
            role=payload.role,
            # A department only scopes a doctor's records; carrying one on any
            # other role would imply a restriction that is never applied.
            department=payload.department if payload.role is UserRole.DOCTOR else None,
        )
    )
    await session.commit()
    await audit_record(
        AuditAction.USER_CREATE,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="user", entity_id=created.id,
        detail={"email": created.email, "role": created.role.value},
        ip_address=client_ip(request), user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    return UserOut.model_validate(created)


@router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(ADMINISTER)])
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    session: DbSession,
    user: CurrentUser,
    request: Request,
) -> UserOut:
    target = await UserRepository(session).get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such staff account.")

    losing_admin = target.role is UserRole.ADMIN and (
        (payload.role is not None and payload.role is not UserRole.ADMIN)
        or payload.is_active is False
    )
    if losing_admin:
        if target.id == user.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "You cannot remove your own administrative access. Ask another "
                "administrator to do it.",
            )
        if await _active_admin_count(session) <= 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This is the only active administrator. Create another one first, "
                "or the hospital will be locked out of its own system.",
            )

    was = {"role": target.role.value, "is_active": target.is_active}

    if payload.full_name is not None:
        target.full_name = payload.full_name.strip()
    if payload.role is not None:
        target.role = payload.role
        if payload.role is not UserRole.DOCTOR:
            target.department = None
    if payload.department is not None and target.role is UserRole.DOCTOR:
        target.department = payload.department
    if payload.is_active is not None:
        target.is_active = payload.is_active

    await session.commit()
    await audit_record(
        AuditAction.USER_UPDATE,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="user", entity_id=target.id,
        detail={
            "email": target.email,
            "from": was,
            "to": {"role": target.role.value, "is_active": target.is_active},
        },
        ip_address=client_ip(request), user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    return UserOut.model_validate(target)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(ADMINISTER)])
async def reset_password(
    user_id: uuid.UUID,
    payload: PasswordResetRequest,
    session: DbSession,
    user: CurrentUser,
    request: Request,
) -> None:
    """Set a new password for a member of staff who cannot sign in.

    There is no "send a reset link": this hospital's staff share a counter and
    an administrator is on site, so the new password is handed over in person.
    """
    target = await UserRepository(session).get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such staff account.")
    target.hashed_password = hash_password(payload.password)
    await session.commit()
    await audit_record(
        AuditAction.USER_UPDATE,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="user", entity_id=target.id,
        detail={"email": target.email, "change": "password_reset"},
        ip_address=client_ip(request), user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
