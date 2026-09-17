"""TPA and insurance claims as reports: the claim register, and what payers still owe.

Finance reports: they need hospital-wide finance rights.
"""
from datetime import date
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.insurance.rules import STATUS_LABEL
from app.reports.definitions import Column, ColumnType, ReportSpec, register

M = ColumnType.MONEY
D = ColumnType.DATE
N = ColumnType.NUMBER
S = ColumnType.STATUS

CLAIMS = ReportSpec(
    key="tpa-claims",
    title="TPA claims",
    description="Claims opened in the period: what was asked, approved, put on the bill, and paid by the payer.",
    columns=[
        Column("claim_number", "Claim"),
        Column("opened_on", "Opened", D),
        Column("patient_name", "Patient"),
        Column("uhid", "UHID", default_visible=False),
        Column("payer_name", "Payer"),
        Column("policy_number", "Policy", default_visible=False),
        Column("external_reference", "Payer's reference", default_visible=False),
        Column("stay_or_bill", "Admission / bill"),
        Column("status", "Status", S),
        Column("pre_auth_approved_paise", "Pre-authorised", M, total=True, default_visible=False),
        Column("claimed_paise", "Claimed", M, total=True),
        Column("approved_paise", "Approved", M, total=True),
        Column("booked_paise", "On the bill", M, total=True),
        Column("received_paise", "Received", M, total=True),
        Column("tds_paise", "TDS", M, total=True),
        Column("deducted_paise", "Disallowed", M, total=True),
        Column("outstanding_paise", "Payer owes", M, total=True),
        Column("check", "Check", default_visible=False),
    ],
)


async def _claims(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    from app.core.clock import to_local
    from app.services.insurance_service import InsuranceService

    rows = []
    for claim in await InsuranceService(session).claims(created_from=date_from, created_to=date_to, limit=5000):
        parts = [claim["admission"]["ip_number"] if claim["admission"] else None,
                 claim["invoice"]["invoice_number"] if claim["invoice"] else None]
        rows.append({
            "claim_number": claim["claim_number"], "opened_on": to_local(claim["created_at"]).date(),
            "patient_name": claim["patient"]["name"], "uhid": claim["patient"]["uhid"] or "",
            "payer_name": claim["payer_name"], "policy_number": claim["policy"]["policy_number"],
            "external_reference": claim["external_reference"] or "",
            "stay_or_bill": " / ".join(p for p in parts if p),
            "status": STATUS_LABEL[claim["status"]],
            **{key: claim[key] for key in ("pre_auth_approved_paise", "claimed_paise", "approved_paise",
                                           "booked_paise", "received_paise", "tds_paise", "deducted_paise",
                                           "outstanding_paise")},
            "check": " ".join(claim["attention"]),
        })
    return rows


OUTSTANDING = ReportSpec(
    key="tpa-outstanding",
    title="TPA outstanding",
    description="Claim amounts put on bills and not yet settled by the payer on the chosen day, with their age.",
    single_day=True,
    columns=[
        Column("payer_name", "Payer"),
        Column("claim_number", "Claim"),
        Column("patient_name", "Patient"),
        Column("uhid", "UHID", default_visible=False),
        Column("external_reference", "Payer's reference", default_visible=False),
        Column("booked_on", "On the bill since", D),
        Column("age_days", "Days", N),
        Column("bucket", "Age"),
        Column("booked_paise", "On the bill", M, total=True),
        Column("settled_paise", "Settled", M, total=True),
        Column("outstanding_paise", "Payer owes", M, total=True),
    ],
)


async def _outstanding(session: AsyncSession, *, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    from app.services.insurance_service import InsuranceService

    result = await InsuranceService(session).outstanding(date_to)
    return [{key: item[key] for key in ("payer_name", "claim_number", "patient_name", "uhid", "external_reference",
                                        "booked_on", "age_days", "bucket", "booked_paise", "settled_paise",
                                        "outstanding_paise")}
            for item in result["items"]]


register(CLAIMS, _claims)
register(OUTSTANDING, _outstanding)
