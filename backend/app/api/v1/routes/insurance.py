"""TPA and insurance claims.

The counter keeps policies, opens and moves claims, and puts an approved
claim's share on the bill (insurance:claim). Recording what a payer actually
paid is accounts work: accounts:manage and the finance PIN, like the rest of
the books.
"""
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import CurrentUser, DbSession, require_permission
from app.api.v1.routes.finance import finance_unlock
from app.core.audit import client_ip, record as audit_record
from app.core.clock import local_today
from app.core.permissions import Permission
from app.models.enums import AuditAction, PayerType
from app.services.insurance_service import InsuranceError, InsuranceService

router = APIRouter(prefix="/insurance", tags=["insurance"])

DESK = [Depends(require_permission(Permission.CLAIM_MANAGE))]
MONEY = [Depends(require_permission(Permission.ACCOUNTS_MANAGE)), Depends(finance_unlock)]


def _fail(exc: InsuranceError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


async def _audit(action: AuditAction, user, request: Request, entity_id, detail: Dict[str, Any],
                 patient_id=None, entity_type: str = "insurance_claim") -> None:
    await audit_record(action, actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
                       entity_type=entity_type, entity_id=entity_id, patient_id=patient_id,
                       ip_address=client_ip(request), detail=detail)


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: uuid.UUID
    organisation_id: Optional[uuid.UUID] = None
    payer_type: PayerType = PayerType.INSURANCE
    insurer_name: str = Field(min_length=1, max_length=255)
    tpa_name: Optional[str] = Field(default=None, max_length=255)
    policy_number: str = Field(min_length=1, max_length=64)
    member_id: Optional[str] = Field(default=None, max_length=64)
    scheme_name: Optional[str] = Field(default=None, max_length=255)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    sum_insured_paise: Optional[int] = Field(default=None, ge=0)
    is_active: bool = True

    @field_validator("payer_type")
    @classmethod
    def _not_self_pay(cls, value: PayerType) -> PayerType:
        if value is PayerType.SELF_PAY:
            raise ValueError("A policy is paid by an insurer, TPA, employer or scheme, not the patient.")
        return value


class ClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: uuid.UUID
    admission_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None
    diagnosis: Optional[str] = Field(default=None, max_length=2000)
    treatment_summary: Optional[str] = Field(default=None, max_length=4000)
    external_reference: Optional[str] = Field(default=None, max_length=120)


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    pre_auth_requested_paise: Optional[int] = Field(default=None, ge=0)
    pre_auth_approved_paise: Optional[int] = Field(default=None, ge=0)
    claimed_paise: Optional[int] = Field(default=None, ge=0)
    approved_paise: Optional[int] = Field(default=None, ge=0)
    patient_liability_paise: Optional[int] = Field(default=None, ge=0)
    external_reference: Optional[str] = Field(default=None, max_length=120)
    reason: Optional[str] = Field(default=None, max_length=1000)
    query: Optional[str] = Field(default=None, max_length=2000)
    note: Optional[str] = Field(default=None, max_length=500)


class BookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_paise: int = Field(gt=0)


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class SettleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    received_on: date
    received_paise: int = Field(default=0, ge=0)
    tds_paise: int = Field(default=0, ge=0)
    deduction_paise: int = Field(default=0, ge=0)
    deduction_reason: Optional[str] = Field(default=None, max_length=500)
    mode: str
    reference: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=1000)


# --------------------------------------------------------------- reading
@router.get("/options", dependencies=DESK)
async def options(session: DbSession) -> Dict[str, Any]:
    return await InsuranceService(session).options()


@router.get("/patients/{patient_id}", dependencies=DESK)
async def patient_context(patient_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    """A patient's policies, recent admissions and bills, and claims — what opening a claim needs."""
    try:
        return await InsuranceService(session).patient_context(patient_id)
    except InsuranceError as exc:
        raise _fail(exc) from exc


@router.get("/claims", dependencies=DESK)
async def list_claims(
    session: DbSession,
    status: Optional[str] = Query(default=None, description="A claim status, or 'open'"),
    organisation_id: Optional[uuid.UUID] = Query(default=None),
    patient_id: Optional[uuid.UUID] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=200, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    try:
        return await InsuranceService(session).claims(status=status, organisation_id=organisation_id,
                                                      patient_id=patient_id, q=q, limit=limit)
    except InsuranceError as exc:
        raise _fail(exc) from exc


@router.get("/claims/{claim_id}", dependencies=DESK)
async def get_claim(claim_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    try:
        out = await InsuranceService(session).claim(claim_id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await session.commit()
    return out


@router.get("/outstanding", dependencies=DESK)
async def outstanding(session: DbSession, as_of: Optional[date] = Query(default=None)) -> Dict[str, Any]:
    """What each payer still owes on claims put on bills, by age."""
    return await InsuranceService(session).outstanding(as_of or local_today())


# --------------------------------------------------------------- policies
async def _save_policy(payload: PolicyIn, session, user, request: Request, policy_id=None) -> Dict[str, Any]:
    service = InsuranceService(session)
    try:
        policy = await service.save_policy(payload.model_dump(), policy_id=policy_id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await session.commit()
    await _audit(AuditAction.POLICY_SAVE, user, request, policy.id,
                 {"created": policy_id is None, "policy_number": policy.policy_number,
                  "insurer": policy.insurer_name, "active": policy.is_active},
                 patient_id=policy.patient_id, entity_type="insurance_policy")
    return service.policy_out(policy)


@router.post("/policies", dependencies=DESK, status_code=201)
async def create_policy(payload: PolicyIn, session: DbSession, user: CurrentUser, request: Request) -> Dict[str, Any]:
    return await _save_policy(payload, session, user, request)


@router.put("/policies/{policy_id}", dependencies=DESK)
async def update_policy(policy_id: uuid.UUID, payload: PolicyIn, session: DbSession, user: CurrentUser,
                        request: Request) -> Dict[str, Any]:
    return await _save_policy(payload, session, user, request, policy_id)


# ----------------------------------------------------------------- claims
@router.post("/claims", dependencies=DESK, status_code=201)
async def create_claim(payload: ClaimIn, session: DbSession, user: CurrentUser, request: Request) -> Dict[str, Any]:
    service = InsuranceService(session)
    try:
        claim = await service.create_claim(payload.model_dump(), by=user.full_name)
        await session.commit()
        out = await service.claim(claim.id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await _audit(AuditAction.CLAIM_CREATE, user, request, claim.id,
                 {"claim_number": claim.claim_number, "payer": claim.payer_name}, patient_id=claim.patient_id)
    return out


@router.post("/claims/{claim_id}/status", dependencies=DESK)
async def move_claim(claim_id: uuid.UUID, payload: MoveIn, session: DbSession, user: CurrentUser,
                     request: Request) -> Dict[str, Any]:
    service = InsuranceService(session)
    try:
        claim, previous = await service.move(claim_id, payload.model_dump(), by=user.full_name)
        await session.commit()
        out = await service.claim(claim_id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await _audit(AuditAction.CLAIM_STATUS, user, request, claim_id,
                 {"claim_number": claim.claim_number, "from": previous, "to": claim.status.value,
                  **{k: v for k, v in payload.model_dump().items() if v is not None and k != "status"}},
                 patient_id=claim.patient_id)
    return out


@router.post("/claims/{claim_id}/book", dependencies=DESK)
async def book_claim(claim_id: uuid.UUID, payload: BookIn, session: DbSession, user: CurrentUser,
                     request: Request) -> Dict[str, Any]:
    service = InsuranceService(session)
    try:
        claim, payment = await service.book(claim_id, payload.amount_paise, by=user.full_name, user_id=user.id)
        await session.commit()
        out = await service.claim(claim_id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await _audit(AuditAction.CLAIM_BOOK, user, request, claim_id,
                 {"claim_number": claim.claim_number, "amount_paise": payload.amount_paise,
                  "receipt_number": payment.receipt_number}, patient_id=claim.patient_id)
    return out


@router.post("/claims/{claim_id}/unbook", dependencies=DESK)
async def unbook_claim(claim_id: uuid.UUID, payload: ReasonIn, session: DbSession, user: CurrentUser,
                       request: Request) -> Dict[str, Any]:
    service = InsuranceService(session)
    try:
        claim = await service.unbook(claim_id, payload.reason, by=user.full_name)
        await session.commit()
        out = await service.claim(claim_id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await _audit(AuditAction.CLAIM_UNBOOK, user, request, claim_id,
                 {"claim_number": claim.claim_number, "reason": payload.reason}, patient_id=claim.patient_id)
    return out


# ------------------------------------------------------------ settlements
@router.post("/claims/{claim_id}/settlements", dependencies=MONEY)
async def record_settlement(claim_id: uuid.UUID, payload: SettleIn, session: DbSession, user: CurrentUser,
                            request: Request) -> Dict[str, Any]:
    service = InsuranceService(session)
    try:
        claim, settlement = await service.settle(claim_id, payload.model_dump(), by=user.full_name)
        await session.commit()
        out = await service.claim(claim_id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await _audit(AuditAction.CLAIM_SETTLE, user, request, claim_id,
                 {"claim_number": claim.claim_number, "settlement_id": str(settlement.id),
                  **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in payload.model_dump().items()
                     if v not in (None, "")}},
                 patient_id=claim.patient_id)
    return out


@router.post("/settlements/{settlement_id}/cancel", dependencies=MONEY)
async def cancel_settlement(settlement_id: uuid.UUID, payload: ReasonIn, session: DbSession, user: CurrentUser,
                            request: Request) -> Dict[str, Any]:
    service = InsuranceService(session)
    try:
        claim, settlement = await service.cancel_settlement(settlement_id, payload.reason, by=user.full_name)
        await session.commit()
        out = await service.claim(claim.id)
    except InsuranceError as exc:
        raise _fail(exc) from exc
    await _audit(AuditAction.CLAIM_SETTLE_CANCEL, user, request, claim.id,
                 {"claim_number": claim.claim_number, "settlement_id": str(settlement.id),
                  "reason": payload.reason}, patient_id=claim.patient_id)
    return out
