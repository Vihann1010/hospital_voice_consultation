"""Dietary endpoints: the diet list, orders on an admission, the kitchen sheet.

Reading a patient's diet and the kitchen sheet is everyday ward work. Ordering
or stopping a diet is clinical charting, held by doctors and nurses. The diet
list is master data.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.clock import local_today
from app.core.permissions import Permission
from app.models.diet import DietMode, DietOrder
from app.models.enums import AuditAction
from app.models.ipd import Admission
from app.services.diet_service import DietError, DietService

router = APIRouter(prefix="/diet", tags=["diet"])

READ = require_permission(Permission.PATIENT_READ)
ORDER = require_permission(Permission.DIET_ORDER)
MASTERS = require_permission(Permission.MASTER_MANAGE)


class DietModeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    is_nil_by_mouth: bool = False
    position: int = Field(default=0, ge=0, le=999)
    is_active: bool = True


class DietOrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode_id: uuid.UUID
    starts_at: Optional[datetime] = None
    instructions: Optional[str] = Field(default=None, max_length=500)


class DietStopIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _fail(exc: DietError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _mode(mode: DietMode) -> Dict[str, Any]:
    return {"id": mode.id, "code": mode.code, "name": mode.name, "description": mode.description,
            "is_nil_by_mouth": mode.is_nil_by_mouth, "position": mode.position, "is_active": mode.is_active}


def _order(order: DietOrder, now: datetime) -> Dict[str, Any]:
    stopped_before_start = order.ends_at is not None and order.ends_at <= order.starts_at
    return {
        "id": order.id, "mode_id": order.mode_id, "mode_name": order.mode_name,
        "is_nil_by_mouth": order.is_nil_by_mouth, "instructions": order.instructions,
        "starts_at": order.starts_at, "ends_at": order.ends_at,
        "ordered_by_name": order.ordered_by_name, "ended_by_name": order.ended_by_name,
        "end_reason": order.end_reason, "created_at": order.created_at,
        "in_effect": (not stopped_before_start and order.starts_at <= now
                      and (order.ends_at is None or now < order.ends_at)),
        "upcoming": order.ends_at is None and order.starts_at > now,
    }


@router.get("/modes", dependencies=[Depends(READ)])
async def list_modes(session: DbSession, include_inactive: bool = Query(default=False)) -> List[Dict[str, Any]]:
    return [_mode(mode) for mode in await DietService(session).modes(include_inactive=include_inactive)]


@router.post("/modes", status_code=201, dependencies=[Depends(MASTERS)])
async def create_mode(payload: DietModeIn, session: DbSession) -> Dict[str, Any]:
    try:
        mode = await DietService(session).save_mode(None, payload.model_dump())
    except DietError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return _mode(mode)


@router.put("/modes/{mode_id}", dependencies=[Depends(MASTERS)])
async def update_mode(mode_id: uuid.UUID, payload: DietModeIn, session: DbSession) -> Dict[str, Any]:
    try:
        mode = await DietService(session).save_mode(mode_id, payload.model_dump())
    except DietError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return _mode(mode)


@router.get("/admissions/{admission_id}", dependencies=[Depends(READ)])
async def admission_diet(admission_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    if await session.get(Admission, admission_id) is None:
        raise HTTPException(404, "Admission not found.")
    now = datetime.now(timezone.utc)
    orders = [_order(order, now) for order in await DietService(session).orders(admission_id)]
    return {
        "current": next((order for order in orders if order["in_effect"]), None),
        "upcoming": next((order for order in orders if order["upcoming"]), None),
        "orders": orders,
    }


@router.post("/admissions/{admission_id}/orders", status_code=201, dependencies=[Depends(ORDER)])
async def place_order(
    admission_id: uuid.UUID, payload: DietOrderIn, session: DbSession, user: CurrentUser, request: Request
) -> Dict[str, Any]:
    try:
        order = await DietService(session).place_order(
            admission_id, mode_id=payload.mode_id, starts_at=payload.starts_at,
            instructions=payload.instructions, user=user,
        )
    except DietError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    admission = await session.get(Admission, admission_id)
    await audit_record(
        AuditAction.DIET_ORDER,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="admission", entity_id=admission_id, patient_id=admission.patient_id,
        ip_address=client_ip(request),
        detail={"diet": order.mode_name, "starts_at": order.starts_at.isoformat(),
                "instructions": order.instructions},
    )
    return _order(order, datetime.now(timezone.utc))


@router.post("/admissions/{admission_id}/stop", dependencies=[Depends(ORDER)])
async def stop_order(
    admission_id: uuid.UUID, payload: DietStopIn, session: DbSession, user: CurrentUser, request: Request
) -> Dict[str, Any]:
    try:
        order = await DietService(session).stop(admission_id, reason=payload.reason, user=user)
    except DietError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    admission = await session.get(Admission, admission_id)
    await audit_record(
        AuditAction.DIET_STOP,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="admission", entity_id=admission_id, patient_id=admission.patient_id,
        ip_address=client_ip(request), detail={"diet": order.mode_name, "reason": payload.reason},
    )
    return _order(order, datetime.now(timezone.utc))


@router.get("/kitchen", dependencies=[Depends(READ)])
async def kitchen_sheet(session: DbSession, on: Optional[date] = Query(default=None)) -> Dict[str, Any]:
    """Every inpatient's diet for each meal of one day."""
    try:
        return await DietService(session).kitchen(on or local_today())
    except DietError as exc:
        raise _fail(exc) from exc
