"""Finance: the day's collections, cash sessions, tariff and insurance.

The reports here answer the questions a hospital actually asks at closing
time — what did we bill, what did we collect, in what form, and does the
drawer match — rather than presenting a general-purpose ledger.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, get_reception_service, require_roles
from app.models.emr import (
    CashSession,
    InsuranceClaim,
    InsurancePolicy,
    Invoice,
    Payment,
    ServiceItem,
    Visit,
)
from app.models.enums import (
    CashSessionStatus,
    ClaimStatus,
    InvoiceStatus,
    UserRole,
)
from app.schemas.emr_schemas import (
    CashSessionCloseRequest,
    CashSessionOpenRequest,
    CashSessionOut,
    ClaimCreateRequest,
    ClaimOut,
    ClaimUpdateRequest,
    CollectionSummaryOut,
    PolicyOut,
    PolicyUpsert,
    ServiceItemOut,
    ServiceItemUpsert,
)
from app.services.reception_service import ReceptionError, ReceptionService

router = APIRouter(prefix="/finance", tags=["finance"])

Service = Annotated[ReceptionService, Depends(get_reception_service)]
DESK = require_roles(UserRole.ADMIN, UserRole.DOCTOR, UserRole.STAFF)
# Revenue across the whole hospital, and the price list, are management data.
MANAGEMENT = require_roles(UserRole.ADMIN, UserRole.DOCTOR)


# -------------------------------------------------------------- collections
@router.get("/collections", response_model=CollectionSummaryOut,
            dependencies=[Depends(MANAGEMENT)])
async def collections(
    session: DbSession,
    on: Optional[date] = Query(default=None, description="Defaults to today"),
) -> CollectionSummaryOut:
    """What was billed and collected on a given day.

    Billed and collected are deliberately separate figures. They differ
    whenever a patient part-pays, a bill goes to insurance, or a refund is
    issued — and conflating them is how a day looks balanced when it is not.
    """
    day = on or date.today()
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)

    billed = await session.execute(
        select(
            func.count(Invoice.id),
            func.count(func.distinct(Invoice.patient_id)),
            func.coalesce(func.sum(Invoice.total_paise), 0),
            func.coalesce(func.sum(Invoice.discount_paise), 0),
            func.coalesce(func.sum(Invoice.total_paise - Invoice.paid_paise), 0),
        ).where(
            Invoice.issued_at.between(start, end),
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    )
    invoice_count, patient_count, billed_paise, discount_paise, outstanding = billed.one()

    # Receipts and refunds are separated so a heavy refund day is visible
    # rather than netted quietly into a lower collection figure.
    modes = await session.execute(
        select(Payment.mode, func.coalesce(func.sum(Payment.amount_paise), 0))
        .where(Payment.received_at.between(start, end))
        .group_by(Payment.mode)
    )
    by_mode = {mode.value: int(amount or 0) for mode, amount in modes.all()}

    refunded = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.received_at.between(start, end), Payment.is_refund.is_(True)
        )
    )
    refunded_paise = abs(int(refunded.scalar_one() or 0))

    collected = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.received_at.between(start, end), Payment.is_refund.is_(False)
        )
    )
    collected_paise = int(collected.scalar_one() or 0)

    departments = await session.execute(
        select(Visit.department, func.coalesce(func.sum(Invoice.total_paise), 0))
        .join(Invoice, Invoice.visit_id == Visit.id)
        .where(
            Invoice.issued_at.between(start, end),
            Invoice.status != InvoiceStatus.CANCELLED,
        )
        .group_by(Visit.department)
    )
    by_department = {
        department.value: int(amount or 0) for department, amount in departments.all()
    }

    return CollectionSummaryOut(
        on=day,
        invoice_count=int(invoice_count or 0),
        patient_count=int(patient_count or 0),
        billed_paise=int(billed_paise or 0),
        discount_paise=int(discount_paise or 0),
        collected_paise=collected_paise,
        refunded_paise=refunded_paise,
        outstanding_paise=int(outstanding or 0),
        by_mode=by_mode,
        by_department=by_department,
    )


@router.get("/outstanding", dependencies=[Depends(MANAGEMENT)])
async def outstanding_invoices(
    session: DbSession, limit: int = Query(default=100, ge=1, le=500)
) -> Dict[str, Any]:
    """Bills with money still due — the follow-up list."""
    result = await session.execute(
        select(Invoice)
        .where(
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]),
            Invoice.total_paise > Invoice.paid_paise,
        )
        .order_by(Invoice.issued_at.desc())
        .limit(limit)
    )
    invoices = list(result.scalars().all())
    return {
        "count": len(invoices),
        "total_outstanding_paise": sum(i.total_paise - i.paid_paise for i in invoices),
        "invoices": [
            {
                "id": str(i.id),
                "invoice_number": i.invoice_number,
                "patient_id": str(i.patient_id),
                "total_paise": i.total_paise,
                "paid_paise": i.paid_paise,
                "balance_paise": i.total_paise - i.paid_paise,
                "issued_at": i.issued_at.isoformat() if i.issued_at else None,
            }
            for i in invoices
        ],
    }


# ------------------------------------------------------------ cash sessions
@router.post("/cash-sessions", response_model=CashSessionOut,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(DESK)])
async def open_cash_session(
    payload: CashSessionOpenRequest, service: Service, user: CurrentUser
) -> CashSessionOut:
    try:
        session_row = await service.open_cash_session(
            cashier_id=user.id, cashier_name=user.full_name,
            counter_name=payload.counter_name,
            opening_float_paise=payload.opening_float_paise,
        )
        await service.session.commit()
    except ReceptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CashSessionOut.model_validate(session_row)


@router.get("/cash-sessions/current", dependencies=[Depends(DESK)])
async def current_cash_session(session: DbSession, user: CurrentUser) -> Dict[str, Any]:
    result = await session.execute(
        select(CashSession).where(
            CashSession.cashier_id == user.id,
            CashSession.status == CashSessionStatus.OPEN,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return {"open": False, "session": None}
    return {"open": True, "session": CashSessionOut.model_validate(row).model_dump()}


@router.post("/cash-sessions/{cash_session_id}/close", dependencies=[Depends(DESK)])
async def close_cash_session(
    cash_session_id: uuid.UUID, payload: CashSessionCloseRequest, service: Service
) -> Dict[str, Any]:
    """Close a shift and reconcile the drawer against what was taken."""
    try:
        row, totals = await service.close_cash_session(
            cash_session_id,
            counted_cash_paise=payload.counted_cash_paise,
            variance_note=payload.variance_note,
        )
        await service.session.commit()
    except ReceptionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {
        "session": CashSessionOut.model_validate(row).model_dump(),
        "totals_by_mode": totals,
    }


# ------------------------------------------------------------------- tariff
@router.get("/services", response_model=List[ServiceItemOut],
            dependencies=[Depends(DESK)])
async def list_services(
    session: DbSession, active_only: bool = Query(default=True)
) -> List[ServiceItemOut]:
    statement = select(ServiceItem).order_by(ServiceItem.category, ServiceItem.name)
    if active_only:
        statement = statement.where(ServiceItem.is_active.is_(True))
    result = await session.execute(statement)
    return [ServiceItemOut.model_validate(item) for item in result.scalars().all()]


@router.put("/services/{code}", response_model=ServiceItemOut,
            dependencies=[Depends(MANAGEMENT)])
async def upsert_service(
    code: str, payload: ServiceItemUpsert, session: DbSession
) -> ServiceItemOut:
    """Create or reprice a service.

    Existing invoices are unaffected: their lines carry the rate that applied
    when the bill was raised.
    """
    result = await session.execute(select(ServiceItem).where(ServiceItem.code == code))
    item = result.scalar_one_or_none()
    if item is None:
        item = ServiceItem(**payload.model_dump())
        session.add(item)
    else:
        for field, value in payload.model_dump().items():
            setattr(item, field, value)
    await session.commit()
    return ServiceItemOut.model_validate(item)


# ---------------------------------------------------------------- insurance
@router.post("/policies", response_model=PolicyOut,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(DESK)])
async def add_policy(payload: PolicyUpsert, session: DbSession) -> PolicyOut:
    policy = InsurancePolicy(
        **payload.model_dump(), balance_paise=payload.sum_insured_paise
    )
    session.add(policy)
    await session.commit()
    return PolicyOut.model_validate(policy)


@router.get("/policies", response_model=List[PolicyOut], dependencies=[Depends(DESK)])
async def list_policies(
    session: DbSession, patient_id: uuid.UUID = Query(...)
) -> List[PolicyOut]:
    result = await session.execute(
        select(InsurancePolicy)
        .where(InsurancePolicy.patient_id == patient_id)
        .order_by(InsurancePolicy.created_at.desc())
    )
    return [PolicyOut.model_validate(policy) for policy in result.scalars().all()]


@router.post("/claims", response_model=ClaimOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(DESK)])
async def create_claim(
    payload: ClaimCreateRequest, session: DbSession, user: CurrentUser
) -> ClaimOut:
    """Open a cashless claim against a policy.

    Transmission to the payer is deliberately out of scope here: every TPA has
    its own portal and form, so this records and tracks the claim's state, and
    the submission itself is done through the payer's own channel.
    """
    policy = await session.get(InsurancePolicy, payload.policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy not found")

    count = await session.execute(select(func.count()).select_from(InsuranceClaim))
    claim = InsuranceClaim(
        claim_number=f"CLM-{date.today():%y%m}-{int(count.scalar_one()) + 1:05d}",
        policy_id=policy.id,
        patient_id=policy.patient_id,
        visit_id=payload.visit_id,
        invoice_id=payload.invoice_id,
        status=ClaimStatus.DRAFT,
        claimed_paise=payload.claimed_paise,
        diagnosis=payload.diagnosis,
        treatment_summary=payload.treatment_summary,
        history=[{
            "at": datetime.now(timezone.utc).isoformat(),
            "status": ClaimStatus.DRAFT.value,
            "by": user.full_name,
        }],
    )
    session.add(claim)
    await session.commit()
    return ClaimOut.model_validate(claim)


@router.patch("/claims/{claim_id}", response_model=ClaimOut, dependencies=[Depends(DESK)])
async def update_claim(
    claim_id: uuid.UUID, payload: ClaimUpdateRequest, session: DbSession,
    user: CurrentUser,
) -> ClaimOut:
    """Advance a claim, recording who moved it and when."""
    claim = await session.get(InsuranceClaim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")

    now = datetime.now(timezone.utc)
    claim.status = payload.status
    for field in ("external_reference", "approved_paise", "settled_paise",
                  "patient_liability_paise", "rejection_reason", "query_detail"):
        value = getattr(payload, field)
        if value is not None:
            setattr(claim, field, value)

    if payload.status is ClaimStatus.SUBMITTED and claim.submitted_at is None:
        claim.submitted_at = now
    if payload.status in (ClaimStatus.APPROVED, ClaimStatus.PARTIALLY_APPROVED,
                          ClaimStatus.REJECTED):
        claim.decided_at = now
    if payload.status is ClaimStatus.SETTLED:
        claim.settled_at = now

    claim.history = list(claim.history or []) + [{
        "at": now.isoformat(),
        "status": payload.status.value,
        "by": user.full_name,
        "note": payload.note,
    }]
    await session.commit()
    return ClaimOut.model_validate(claim)


@router.get("/claims", response_model=List[ClaimOut], dependencies=[Depends(DESK)])
async def list_claims(
    session: DbSession,
    patient_id: Optional[uuid.UUID] = Query(default=None),
    claim_status: Optional[ClaimStatus] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[ClaimOut]:
    statement = select(InsuranceClaim).order_by(InsuranceClaim.created_at.desc()).limit(limit)
    if patient_id is not None:
        statement = statement.where(InsuranceClaim.patient_id == patient_id)
    if claim_status is not None:
        statement = statement.where(InsuranceClaim.status == claim_status)
    result = await session.execute(statement)
    return [ClaimOut.model_validate(claim) for claim in result.scalars().all()]
