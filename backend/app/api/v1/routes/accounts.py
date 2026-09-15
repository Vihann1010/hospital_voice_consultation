"""The books and consultant payouts.

Under /finance, behind the finance PIN like the rest of the hospital's money.
Reading the books needs finance rights; posting a voucher, changing the chart
and running payouts needs accounts management.
"""
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.accounts.payout import CATEGORIES
from app.accounts.worker import JOB as POSTING_JOB, run_books_posting
from app.api.deps import CurrentUser, DbSession, require_permission
from app.api.v1.routes.finance import finance_unlock
from app.core.audit import client_ip, record as audit_record
from app.core.clock import local_today
from app.core.financial_year import current as current_year
from app.core.permissions import Permission
from app.models.accounts import ConsultantPayout, ConsultantPayoutItem
from app.models.consultant import Consultant
from app.models.enums import AuditAction
from app.models.job_run import JobRun
from app.services.accounts_service import AccountsError, AccountsService
from app.services.payout_service import PayoutService

router = APIRouter(prefix="/finance/accounts", tags=["accounts"])

READ = [Depends(require_permission(Permission.FINANCE_READ)), Depends(finance_unlock)]
MANAGE = [Depends(require_permission(Permission.ACCOUNTS_MANAGE)), Depends(finance_unlock)]


def _fail(exc: AccountsError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _range(date_from: Optional[date], date_to: Optional[date]):
    return date_from or current_year().start, date_to or local_today()


async def _audit(action: AuditAction, user, request: Request, entity_type: str, entity_id, detail: Dict[str, Any]):
    await audit_record(action, actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
                       entity_type=entity_type, entity_id=entity_id, ip_address=client_ip(request), detail=detail)


# ---------------------------------------------------------------- posting
def _run(run: JobRun) -> Dict[str, Any]:
    return {"id": run.id, "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at,
            "triggered_by": run.triggered_by, "summary": run.summary or {}, "error": run.error}


@router.get("/runs", dependencies=READ)
async def posting_runs(session: DbSession, limit: int = Query(default=10, ge=1, le=100)) -> List[Dict[str, Any]]:
    runs = (await session.execute(select(JobRun).where(JobRun.job == POSTING_JOB)
                                  .order_by(JobRun.started_at.desc()).limit(limit))).scalars()
    return [_run(run) for run in runs]


@router.post("/post", dependencies=MANAGE)
async def post_now(user: CurrentUser, request: Request, full: bool = Query(default=False)) -> Dict[str, Any]:
    run = await run_books_posting(triggered_by=user.full_name, full=full)
    await _audit(AuditAction.BOOKS_POSTING_RUN, user, request, "job_run", run.id,
                 {"full": full, "status": run.status,
                  **{k: v for k, v in (run.summary or {}).items() if k != "exceptions"}})
    return _run(run)


# ---------------------------------------------------------------- ledgers
class LedgerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=1, max_length=32)
    group_id: uuid.UUID
    opening_balance_paise: int = 0
    is_active: bool = True
    notes: Optional[str] = Field(default=None, max_length=1000)


@router.get("/groups", dependencies=READ)
async def groups(session: DbSession) -> List[Dict[str, Any]]:
    return [{"id": g.id, "code": g.code, "name": g.name, "nature": g.nature, "parent_id": g.parent_id,
             "is_system": g.is_system} for g in await AccountsService(session).groups()]


@router.get("/ledgers", dependencies=READ)
async def ledgers(session: DbSession, as_of: Optional[date] = Query(default=None)) -> List[Dict[str, Any]]:
    return await AccountsService(session).ledgers(as_of=as_of)


@router.post("/ledgers", status_code=201, dependencies=MANAGE)
async def create_ledger(payload: LedgerIn, session: DbSession) -> Dict[str, Any]:
    try:
        ledger = await AccountsService(session).save_ledger(None, payload.model_dump())
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return {"id": ledger.id}


@router.put("/ledgers/{ledger_id}", dependencies=MANAGE)
async def update_ledger(ledger_id: uuid.UUID, payload: LedgerIn, session: DbSession) -> Dict[str, Any]:
    try:
        ledger = await AccountsService(session).save_ledger(ledger_id, payload.model_dump())
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return {"id": ledger.id}


@router.get("/ledgers/{ledger_id}/statement", dependencies=READ)
async def ledger_statement(ledger_id: uuid.UUID, session: DbSession,
                           date_from: Optional[date] = Query(default=None, alias="from"),
                           date_to: Optional[date] = Query(default=None, alias="to")) -> Dict[str, Any]:
    start, end = _range(date_from, date_to)
    try:
        return await AccountsService(session).statement(ledger_id, start, end)
    except AccountsError as exc:
        raise _fail(exc) from exc


@router.get("/trial-balance", dependencies=READ)
async def trial_balance(session: DbSession,
                        date_from: Optional[date] = Query(default=None, alias="from"),
                        date_to: Optional[date] = Query(default=None, alias="to")) -> Dict[str, Any]:
    start, end = _range(date_from, date_to)
    try:
        return await AccountsService(session).trial_balance(start, end)
    except AccountsError as exc:
        raise _fail(exc) from exc


# --------------------------------------------------------------- vouchers
class VoucherLineIn(BaseModel):
    ledger_id: uuid.UUID
    debit_paise: int = Field(default=0, ge=0)
    credit_paise: int = Field(default=0, ge=0)
    narration: Optional[str] = Field(default=None, max_length=500)


class VoucherIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voucher_type: str
    voucher_date: date
    narration: str = Field(min_length=3, max_length=1000)
    lines: List[VoucherLineIn] = Field(min_length=2, max_length=50)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.get("/vouchers", dependencies=READ)
async def vouchers(session: DbSession,
                   date_from: Optional[date] = Query(default=None, alias="from"),
                   date_to: Optional[date] = Query(default=None, alias="to"),
                   voucher_type: Optional[str] = Query(default=None, alias="type"),
                   q: Optional[str] = Query(default=None, max_length=80),
                   limit: int = Query(default=500, ge=1, le=2000)) -> List[Dict[str, Any]]:
    start, end = _range(date_from, date_to)
    return await AccountsService(session).vouchers(date_from=start, date_to=end, voucher_type=voucher_type,
                                                   q=q, limit=limit)


@router.get("/vouchers/{voucher_id}", dependencies=READ)
async def voucher(voucher_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    try:
        return await AccountsService(session).voucher(voucher_id)
    except AccountsError as exc:
        raise _fail(exc) from exc


@router.post("/vouchers", status_code=201, dependencies=MANAGE)
async def create_voucher(payload: VoucherIn, session: DbSession, user: CurrentUser, request: Request) -> Dict[str, Any]:
    service = AccountsService(session)
    try:
        created = await service.create_manual(
            voucher_type=payload.voucher_type, on=payload.voucher_date, narration=payload.narration,
            lines=[line.model_dump() for line in payload.lines], created_by_name=user.full_name,
        )
        await session.commit()
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.VOUCHER_CREATE, user, request, "voucher", created.id,
                 {"voucher_number": created.voucher_number, "type": created.voucher_type,
                  "amount_paise": sum(line.debit_paise for line in payload.lines)})
    return await service.voucher(created.id)


@router.post("/vouchers/{voucher_id}/reverse", dependencies=MANAGE)
async def reverse_voucher(voucher_id: uuid.UUID, payload: ReasonIn, session: DbSession, user: CurrentUser,
                          request: Request) -> Dict[str, Any]:
    service = AccountsService(session)
    try:
        reversal = await service.reverse_manual(voucher_id, reason=payload.reason, by=user.full_name)
        await session.commit()
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.VOUCHER_REVERSE, user, request, "voucher", voucher_id,
                 {"reversal": reversal.voucher_number, "reason": payload.reason})
    return await service.voucher(reversal.id)


# ---------------------------------------------------------------- payouts
class TermsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_percent: int = Field(ge=0, le=100)
    categories: List[str] = Field(default_factory=lambda: ["consultation"])


class PayoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consultant_id: uuid.UUID
    date_from: date
    date_to: date
    notes: Optional[str] = Field(default=None, max_length=1000)


class PayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    reference: Optional[str] = Field(default=None, max_length=120)
    tds_paise: int = Field(default=0, ge=0)
    paid_on: date


def _consultant(c: Consultant) -> Dict[str, Any]:
    return {"id": c.id, "full_name": c.full_name, "department": c.department.value,
            "payout_share_percent": c.payout_share_percent,
            "payout_categories": c.payout_categories or ["consultation"], "is_active": c.is_active}


def _payout(p: ConsultantPayout, items: Optional[List[ConsultantPayoutItem]] = None) -> Dict[str, Any]:
    out = {k: getattr(p, k) for k in (
        "id", "payout_number", "consultant_id", "consultant_name", "period_from", "period_to", "share_percent",
        "base_paise", "share_paise", "tds_paise", "net_paid_paise", "status", "approved_at", "approved_by_name",
        "paid_at", "paid_on", "paid_by_name", "payment_mode", "payment_reference", "cancelled_at",
        "cancelled_by_name", "cancel_reason", "accrual_voucher_id", "payment_voucher_id", "notes")}
    out["categories"] = [c for c in (p.categories or "").split(",") if c]
    if items is not None:
        out["items"] = [{k: getattr(i, k) for k in (
            "kind", "invoice_id", "payment_id", "invoice_number", "invoice_date", "patient_name",
            "eligible_paise", "base_paise", "share_paise")} for i in items]
    return out


@router.get("/payout-options", dependencies=READ)
async def payout_options(session: DbSession) -> Dict[str, Any]:
    consultants = (await session.execute(select(Consultant).order_by(Consultant.full_name))).scalars()
    return {"categories": list(CATEGORIES), "pay_modes": ["cash", "upi", "net_banking", "cheque"],
            "consultants": [_consultant(c) for c in consultants]}


@router.put("/consultants/{consultant_id}/payout-terms", dependencies=MANAGE)
async def set_payout_terms(consultant_id: uuid.UUID, payload: TermsIn, session: DbSession, user: CurrentUser,
                           request: Request) -> Dict[str, Any]:
    try:
        consultant = await PayoutService(session).set_terms(consultant_id, percent=payload.share_percent,
                                                            categories=payload.categories)
        await session.commit()
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.PAYOUT_TERMS, user, request, "consultant", consultant_id, payload.model_dump())
    return _consultant(consultant)


@router.get("/payouts/preview", dependencies=READ)
async def payout_preview(session: DbSession, consultant_id: uuid.UUID = Query(...),
                         date_from: date = Query(..., alias="from"),
                         date_to: date = Query(..., alias="to")) -> Dict[str, Any]:
    try:
        return await PayoutService(session).preview(consultant_id, date_from, date_to)
    except AccountsError as exc:
        raise _fail(exc) from exc


@router.get("/payouts", dependencies=READ)
async def payouts(session: DbSession, date_from: Optional[date] = Query(default=None, alias="from"),
                  date_to: Optional[date] = Query(default=None, alias="to"),
                  consultant_id: Optional[uuid.UUID] = Query(default=None)) -> List[Dict[str, Any]]:
    return [_payout(p) for p in await PayoutService(session).list(date_from=date_from, date_to=date_to,
                                                                  consultant_id=consultant_id)]


@router.get("/payouts/{payout_id}", dependencies=READ)
async def payout(payout_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    try:
        found, items = await PayoutService(session).get(payout_id)
    except AccountsError as exc:
        raise _fail(exc) from exc
    return _payout(found, items)


@router.post("/payouts", status_code=201, dependencies=MANAGE)
async def approve_payout(payload: PayoutIn, session: DbSession, user: CurrentUser, request: Request) -> Dict[str, Any]:
    service = PayoutService(session)
    try:
        created = await service.approve(payload.consultant_id, payload.date_from, payload.date_to,
                                        notes=payload.notes, user=user)
        await session.commit()
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.PAYOUT_APPROVE, user, request, "consultant_payout", created.id,
                 {"payout_number": created.payout_number, "consultant": created.consultant_name,
                  "share_paise": created.share_paise, "period": f"{payload.date_from} to {payload.date_to}"})
    found, items = await service.get(created.id)
    return _payout(found, items)


@router.post("/payouts/{payout_id}/pay", dependencies=MANAGE)
async def pay_payout(payout_id: uuid.UUID, payload: PayIn, session: DbSession, user: CurrentUser,
                     request: Request) -> Dict[str, Any]:
    service = PayoutService(session)
    try:
        paid = await service.pay(payout_id, mode=payload.mode, reference=payload.reference,
                                 tds_paise=payload.tds_paise, paid_on=payload.paid_on, user=user)
        await session.commit()
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.PAYOUT_PAY, user, request, "consultant_payout", payout_id,
                 {"payout_number": paid.payout_number, "net_paid_paise": paid.net_paid_paise,
                  "tds_paise": paid.tds_paise, "mode": paid.payment_mode})
    found, items = await service.get(payout_id)
    return _payout(found, items)


@router.post("/payouts/{payout_id}/cancel", dependencies=MANAGE)
async def cancel_payout(payout_id: uuid.UUID, payload: ReasonIn, session: DbSession, user: CurrentUser,
                        request: Request) -> Dict[str, Any]:
    service = PayoutService(session)
    try:
        cancelled = await service.cancel(payout_id, reason=payload.reason, user=user)
        await session.commit()
    except AccountsError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.PAYOUT_CANCEL, user, request, "consultant_payout", payout_id,
                 {"payout_number": cancelled.payout_number, "reason": payload.reason})
    found, items = await service.get(payout_id)
    return _payout(found, items)
