"""Finance: the day's collections, cash sessions and tariff.

Insurance policies and TPA claims live in app/api/v1/routes/insurance.py.

The reports here answer the questions a hospital actually asks at closing
time — what did we bill, what did we collect, in what form, and does the
drawer match — rather than presenting a general-purpose ledger.
"""
import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, get_reception_service, require_permission
from app.core.permissions import Permission
from app.core.config import settings
from app.core.security import (
    TOKEN_TYPE_FINANCE_UNLOCK,
    create_finance_unlock_token,
    decode_token,
)
from app.models.emr import (
    CashSession,
    Invoice,
    Payment,
    ServiceItem,
    Visit,
    WalletEntry,
)
from app.models.enums import (
    CashSessionStatus,
    InvoiceStatus,
    PaymentMode,
    UserRole,
    WalletEntryKind,
)
from app.schemas.emr_schemas import (
    CashSessionCloseRequest,
    CashSessionOpenRequest,
    CashSessionOut,
    CollectionSummaryOut,
    ServiceItemOut,
    ServiceItemUpsert,
)
from app.services.reception_service import ReceptionError, ReceptionService
from app.core.clock import day_bounds, local_today

router = APIRouter(prefix="/finance", tags=["finance"])

Service = Annotated[ReceptionService, Depends(get_reception_service)]
DESK = require_permission(Permission.PAYMENT_COLLECT)
# Revenue across the whole hospital, and the price list, are management data.
MANAGEMENT = require_permission(Permission.FINANCE_READ)


class FinancePinRequest(BaseModel):
    pin: str


async def finance_unlock(
    user: CurrentUser,
    unlock_token: str | None = Header(default=None, alias="X-Finance-Unlock"),
) -> None:
    claims = decode_token(unlock_token or "")
    if (
        not claims
        or claims.get("type") != TOKEN_TYPE_FINANCE_UNLOCK
        or claims.get("sub") != str(user.id)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Finance PIN required")


FINANCE_MANAGEMENT = [Depends(MANAGEMENT), Depends(finance_unlock)]
# Changing what a service costs is a separate power from seeing what the
# hospital earned, and is held by a separate permission.
REPRICE = [Depends(require_permission(Permission.TARIFF_MANAGE)), Depends(finance_unlock)]


@router.post("/verify-pin")
async def verify_finance_pin(payload: FinancePinRequest, user: CurrentUser) -> dict[str, str]:
    if not secrets.compare_digest(payload.pin, settings.FINANCE_PIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid finance PIN")
    return {"token": create_finance_unlock_token(user_id=user.id, role=user.role.value)}


# -------------------------------------------------------------- collections
@router.get("/collections", response_model=CollectionSummaryOut,
            dependencies=FINANCE_MANAGEMENT)
async def collections(
    session: DbSession,
    on: Optional[date] = Query(default=None, description="Defaults to today"),
) -> CollectionSummaryOut:
    """What was billed and collected on a given day.

    Billed and collected are deliberately separate figures. They differ
    whenever a patient part-pays, a bill goes to insurance, or a refund is
    issued — and conflating them is how a day looks balanced when it is not.
    """
    day = on or local_today()
    # The hospital's day, not the server's. Slicing a UTC column at UTC
    # midnight would put everything collected before 05:30 IST into
    # yesterday's takings.
    start, end = day_bounds(day)

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
    # Till modes only. Wallet-mode rows are settlements against credit, not
    # instruments, and are reported on their own line below.
    modes = await session.execute(
        select(Payment.mode, func.coalesce(func.sum(Payment.amount_paise), 0))
        .where(
            Payment.received_at >= start,
            Payment.received_at < end,
            Payment.mode != PaymentMode.WALLET,
            Payment.cancelled_at.is_(None),
        )
        .group_by(Payment.mode)
    )
    by_mode = {mode.value: int(amount or 0) for mode, amount in modes.all()}

    from_wallet = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.received_at >= start,
            Payment.received_at < end,
            Payment.mode == PaymentMode.WALLET,
            Payment.is_refund.is_(False),
            Payment.cancelled_at.is_(None),
        )
    )
    settled_from_wallet_paise = int(from_wallet.scalar_one() or 0)

    # Wallet-mode payments are excluded from both figures on purpose. That
    # money was collected — and counted — on the day it was deposited;
    # counting it again when it is spent would bank the same rupee twice and
    # make the day irreconcilable against the drawer. The deposit itself is
    # counted separately below, because it is real money arriving today.
    till = [
        Payment.received_at >= start,
        Payment.received_at < end,
        Payment.mode != PaymentMode.WALLET,
        # A struck receipt records money that never moved; the cash ledger and
        # the daily closing already leave it out, and this figure must agree.
        Payment.cancelled_at.is_(None),
        # The insurer's share put on a bill is not money in hand; it arrives
        # later as a claim settlement. It still shows under by_mode.
        Payment.mode != PaymentMode.INSURANCE,
    ]

    refunded = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            *till, Payment.is_refund.is_(True)
        )
    )
    refunded_paise = abs(int(refunded.scalar_one() or 0))

    collected = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            *till, Payment.is_refund.is_(False)
        )
    )
    collected_paise = int(collected.scalar_one() or 0)

    # Advances taken today and balances handed back today. Neither passes
    # through an invoice, so neither appears above — but both moved through
    # the drawer and have to be in the day's total.
    wallet_moves = await session.execute(
        select(WalletEntry.kind, func.coalesce(func.sum(WalletEntry.amount_paise), 0))
        .where(
            WalletEntry.created_at >= start,
            WalletEntry.created_at < end,
            WalletEntry.kind.in_(
                (WalletEntryKind.DEPOSIT, WalletEntryKind.WITHDRAWAL)
            ),
        )
        .group_by(WalletEntry.kind)
    )
    wallet_by_kind = {kind: int(amount or 0) for kind, amount in wallet_moves.all()}
    deposits_paise = wallet_by_kind.get(WalletEntryKind.DEPOSIT, 0)
    withdrawals_paise = abs(wallet_by_kind.get(WalletEntryKind.WITHDRAWAL, 0))
    collected_paise += deposits_paise
    refunded_paise += withdrawals_paise
    if deposits_paise:
        by_mode["wallet_deposit"] = deposits_paise
    if withdrawals_paise:
        by_mode["wallet_withdrawal"] = -withdrawals_paise

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
        settled_from_wallet_paise=settled_from_wallet_paise,
        by_mode=by_mode,
        by_department=by_department,
    )


@router.get("/outstanding", dependencies=FINANCE_MANAGEMENT)
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
    cash_result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.cash_session_id == row.id,
            Payment.mode == PaymentMode.CASH,
            Payment.is_refund.is_(False),
        )
    )
    cash_taken_paise = int(cash_result.scalar_one() or 0)
    return {
        "open": True,
        "session": CashSessionOut.model_validate(row).model_dump(),
        "cash_taken_paise": cash_taken_paise,
        "expected_cash_paise": row.opening_float_paise + cash_taken_paise,
    }


@router.post("/cash-sessions/{cash_session_id}/close", dependencies=[Depends(DESK)])
async def close_cash_session(
    cash_session_id: uuid.UUID, payload: CashSessionCloseRequest,
    service: Service, user: CurrentUser,
) -> Dict[str, Any]:
    """Close a shift and reconcile the drawer against what was taken."""
    try:
        row, totals = await service.close_cash_session(
            cash_session_id,
            counted_cash_paise=payload.counted_cash_paise,
            variance_note=payload.variance_note,
            cashier_id=user.id,
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
            dependencies=REPRICE)
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
