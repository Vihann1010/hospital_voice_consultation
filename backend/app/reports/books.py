"""The books as reports, for export: trial balance, day book, consultant payouts.

Finance reports: they need hospital-wide finance rights. They read the books as
posted; run "Post to books" first if the counter has been busy since the last
scheduled run.
"""
from datetime import date
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import to_local
from app.models.accounts import ConsultantPayout
from app.reports.definitions import Column, ColumnType, ReportSpec, register

M = ColumnType.MONEY
D = ColumnType.DATE
S = ColumnType.STATUS

TRIAL_BALANCE = ReportSpec(
    key="trial-balance",
    title="Trial balance",
    description="Every ledger's opening balance, debits, credits and closing balance for the period.",
    columns=[
        Column("group_path", "Group"),
        Column("code", "Code", default_visible=False),
        Column("name", "Ledger"),
        Column("opening_paise", "Opening (Dr +)", M, total=True),
        Column("debit_paise", "Debit", M, total=True),
        Column("credit_paise", "Credit", M, total=True),
        Column("closing_paise", "Closing (Dr +)", M, total=True),
    ],
)


async def _trial_balance(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    from app.services.accounts_service import AccountsService

    result = await AccountsService(session).trial_balance(date_from, date_to)
    return [{key: row[key] for key in ("group_path", "code", "name", "opening_paise", "debit_paise",
                                        "credit_paise", "closing_paise")} for row in result["rows"]]


DAY_BOOK = ReportSpec(
    key="day-book",
    title="Day book",
    description="Every voucher in the books for the period.",
    columns=[
        Column("voucher_date", "Date", D),
        Column("voucher_number", "Voucher"),
        Column("voucher_type", "Type", S),
        Column("narration", "Narration"),
        Column("total_paise", "Amount", M, total=True),
        Column("status", "Status", S),
        Column("source_type", "From", default_visible=False),
        Column("created_by_name", "By", default_visible=False),
    ],
)


async def _day_book(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    from app.services.accounts_service import AccountsService

    rows = await AccountsService(session).vouchers(date_from=date_from, date_to=date_to, limit=5000)
    return [{key: row[key] for key in ("voucher_date", "voucher_number", "voucher_type", "narration",
                                        "total_paise", "status", "created_by_name")}
            | {"source_type": row["source_type"] or ""} for row in rows]


PAYOUTS = ReportSpec(
    key="consultant-payouts",
    title="Consultant payouts",
    description="Payout runs approved in the period, with shares, TDS and what was paid.",
    columns=[
        Column("payout_number", "Payout"),
        Column("consultant_name", "Consultant"),
        Column("period", "Period"),
        Column("approved_on", "Approved", D),
        Column("share_percent", "Share %", ColumnType.NUMBER),
        Column("base_paise", "Base", M, total=True),
        Column("share_paise", "Share", M, total=True),
        Column("tds_paise", "TDS", M, total=True),
        Column("net_paid_paise", "Paid", M, total=True),
        Column("paid_on", "Paid on", D),
        Column("payment_mode", "Mode", S),
        Column("status", "Status", S),
    ],
)


async def _payouts(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    rows = []
    for payout in (await session.execute(select(ConsultantPayout).order_by(ConsultantPayout.approved_at))).scalars():
        approved_on = to_local(payout.approved_at).date()
        if not date_from <= approved_on <= date_to:
            continue
        cancelled = payout.status == "cancelled"
        rows.append({
            "payout_number": payout.payout_number, "consultant_name": payout.consultant_name,
            "period": f"{payout.period_from:%d %b %Y} - {payout.period_to:%d %b %Y}",
            "approved_on": approved_on, "share_percent": payout.share_percent,
            "base_paise": 0 if cancelled else payout.base_paise,
            "share_paise": 0 if cancelled else payout.share_paise,
            "tds_paise": payout.tds_paise, "net_paid_paise": payout.net_paid_paise,
            "paid_on": payout.paid_on, "payment_mode": payout.payment_mode or "", "status": payout.status,
        })
    return rows


register(TRIAL_BALANCE, _trial_balance)
register(DAY_BOOK, _day_book)
register(PAYOUTS, _payouts)
