"""The seven laboratory reports.

Six are clinical and carry no money: the lab register, test-wise counts, the
pending list, turnaround, critical results and culture. They are open to
anyone who may read a patient's record. The seventh, lab billing, is money and
needs finance rights like every other hospital-wide collection report.

Receipts and refunds for lab bills are ordinary receipts and refunds, and
already appear in the front-office receipt and refund reports; they are not
counted a second time here.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import day_bounds, to_local
from app.lab.rules import CRITICAL_FLAGS, SUSCEPTIBILITY
from app.models.emr import Invoice
from app.models.enums import InvoiceStatus
from app.models.ipd import Admission
from app.models.lab import LabRequest, LabRequestItem
from app.models.patient import Patient
from app.reports.definitions import Column, ColumnType, ReportSpec, register

T = ColumnType.TEXT
N = ColumnType.NUMBER
M = ColumnType.MONEY
DT = ColumnType.DATETIME
S = ColumnType.STATUS
CLINICAL = "patient:read"


def _window(date_from: date, date_to: date):
    return day_bounds(date_from)[0], day_bounds(date_to)[1]


async def _requests(session: AsyncSession, date_from: date, date_to: date):
    start, end = _window(date_from, date_to)
    return (await session.execute(
        select(LabRequest, Patient, Admission)
        .join(Patient, Patient.id == LabRequest.patient_id)
        .outerjoin(Admission, Admission.id == LabRequest.admission_id)
        .options(selectinload(LabRequest.items))
        .where(LabRequest.created_at >= start, LabRequest.created_at < end)
        .order_by(LabRequest.created_at)
    )).all()


async def _verified_items(session: AsyncSession, date_from: date, date_to: date, *, culture=None):
    start, end = _window(date_from, date_to)
    statement = (
        select(LabRequestItem, LabRequest, Patient)
        .join(LabRequest, LabRequest.id == LabRequestItem.request_id)
        .join(Patient, Patient.id == LabRequest.patient_id)
        .where(LabRequestItem.status == "verified", LabRequestItem.verified_at >= start,
               LabRequestItem.verified_at < end)
        .order_by(LabRequestItem.verified_at)
    )
    if culture is not None:
        statement = statement.where(LabRequestItem.is_culture.is_(culture))
    return (await session.execute(statement)).all()


# ------------------------------------------------------------ lab register
LAB_REGISTER = ReportSpec(
    key="lab-register",
    title="Lab register",
    description="Every laboratory request registered, with its tests, billing and status.",
    permission=CLINICAL,
    columns=[
        Column("registered_at", "Registered", DT),
        Column("lab_number", "Lab no."),
        Column("patient_name", "Patient"),
        Column("uhid", "UHID", default_visible=False),
        Column("ip_number", "IP no."),
        Column("tests", "Tests"),
        Column("test_count", "Tests (n)", N, total=True),
        Column("referred_by", "Referred by"),
        Column("priority", "Priority", S),
        Column("billing", "Billing", S),
        Column("status", "Status", S),
        Column("registered_by", "Registered by", default_visible=False),
    ],
)


async def _lab_register(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    rows = []
    for request, patient, admission in await _requests(session, date_from, date_to):
        live = [item for item in request.items if item.status != "cancelled"]
        rows.append({
            "registered_at": to_local(request.created_at),
            "lab_number": request.lab_number,
            "patient_name": patient.name,
            "uhid": patient.uhid or "",
            "ip_number": admission.ip_number if admission else "",
            "tests": ", ".join(item.name for item in live) or "(all cancelled)",
            "test_count": len(live),
            "referred_by": request.referred_by or "",
            "priority": request.priority,
            "billing": request.billing,
            "status": request.status,
            "registered_by": request.registered_by_name,
        })
    return rows


# ---------------------------------------------------------------- test-wise
TEST_WISE = ReportSpec(
    key="lab-test-wise",
    title="Lab test-wise count",
    description="How many of each test were registered, verified, pending and cancelled.",
    permission=CLINICAL,
    columns=[
        Column("test", "Test"),
        Column("group", "Group"),
        Column("registered", "Registered", N, total=True),
        Column("verified", "Verified", N, total=True),
        Column("pending", "Pending", N, total=True),
        Column("cancelled", "Cancelled", N, total=True),
    ],
)


async def _test_wise(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    counts: Dict[str, Dict[str, Any]] = {}
    for request, _patient, _admission in await _requests(session, date_from, date_to):
        for item in request.items:
            entry = counts.setdefault(item.code, {"test": item.name, "group": item.group_name, "registered": 0,
                                                  "verified": 0, "pending": 0, "cancelled": 0})
            entry["registered"] += 1
            if item.status == "verified":
                entry["verified"] += 1
            elif item.status == "cancelled":
                entry["cancelled"] += 1
            else:
                entry["pending"] += 1
    return sorted(counts.values(), key=lambda row: (-row["registered"], row["test"]))


# ------------------------------------------------------------------ pending
PENDING = ReportSpec(
    key="lab-pending",
    title="Lab pending results",
    description="Tests registered in the period and not yet verified, with how long each has waited.",
    permission=CLINICAL,
    columns=[
        Column("registered_at", "Registered", DT),
        Column("lab_number", "Lab no."),
        Column("patient_name", "Patient"),
        Column("test", "Test"),
        Column("status", "Stage", S),
        Column("priority", "Priority", S),
        Column("hours_waiting", "Hours waiting", N),
        Column("overdue", "Overdue"),
    ],
)


async def _pending(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    from app.models.lab import LabTest

    now = datetime.now(timezone.utc)
    turnaround = {test.id: test.turnaround_hours for test in (await session.execute(select(LabTest))).scalars()}
    rows = []
    for request, patient, _admission in await _requests(session, date_from, date_to):
        for item in request.items:
            if item.status in ("verified", "cancelled"):
                continue
            waited = (now - request.created_at).total_seconds() / 3600
            limit = turnaround.get(item.test_id)
            rows.append({
                "registered_at": to_local(request.created_at),
                "lab_number": request.lab_number,
                "patient_name": patient.name,
                "test": item.name,
                "status": item.status,
                "priority": request.priority,
                "hours_waiting": round(waited),
                "overdue": "Yes" if limit and waited > limit else "",
            })
    return rows


# --------------------------------------------------------------- turnaround
TURNAROUND = ReportSpec(
    key="lab-turnaround",
    title="Lab turnaround time",
    description="Verified tests, from registration to verification, against each test's promised time.",
    permission=CLINICAL,
    columns=[
        Column("verified_at", "Verified", DT),
        Column("lab_number", "Lab no."),
        Column("patient_name", "Patient"),
        Column("test", "Test"),
        Column("registered_at", "Registered", DT, default_visible=False),
        Column("collected_at", "Collected", DT, default_visible=False),
        Column("minutes", "Minutes taken", N),
        Column("promised_hours", "Promised (h)", N),
        Column("within", "Within time"),
    ],
)


async def _turnaround(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    from app.models.lab import LabTest

    promised = {test.id: test.turnaround_hours for test in (await session.execute(select(LabTest))).scalars()}
    rows = []
    for item, request, patient in await _verified_items(session, date_from, date_to):
        minutes = round((item.verified_at - request.created_at).total_seconds() / 60)
        hours = promised.get(item.test_id)
        rows.append({
            "verified_at": to_local(item.verified_at),
            "lab_number": request.lab_number,
            "patient_name": patient.name,
            "test": item.name,
            "registered_at": to_local(request.created_at),
            "collected_at": to_local(request.sample_collected_at) if request.sample_collected_at else None,
            "minutes": minutes,
            "promised_hours": hours or 0,
            "within": ("Yes" if minutes <= hours * 60 else "No") if hours else "",
        })
    return rows


# ----------------------------------------------------------------- critical
CRITICAL = ReportSpec(
    key="lab-critical",
    title="Lab critical results",
    description="Verified results in the critical band, and who was told.",
    permission=CLINICAL,
    columns=[
        Column("verified_at", "Verified", DT),
        Column("lab_number", "Lab no."),
        Column("patient_name", "Patient"),
        Column("test", "Test"),
        Column("values", "Critical values"),
        Column("informed", "Informed"),
        Column("verified_by", "Verified by"),
    ],
)


async def _critical(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    rows = []
    for item, request, patient in await _verified_items(session, date_from, date_to, culture=False):
        critical = [row for row in item.results or [] if row.get("flag") in CRITICAL_FLAGS]
        if not critical:
            continue
        rows.append({
            "verified_at": to_local(item.verified_at),
            "lab_number": request.lab_number,
            "patient_name": patient.name,
            "test": item.name,
            "values": "; ".join(f"{row['name']} {row['value']} {row.get('unit') or ''}".strip() for row in critical),
            "informed": item.critical_note or "",
            "verified_by": item.verified_by_name or "",
        })
    return rows


# ------------------------------------------------------------------ culture
CULTURE = ReportSpec(
    key="lab-culture",
    title="Culture and sensitivity",
    description="Verified cultures: organism isolated, and what it was resistant and sensitive to.",
    permission=CLINICAL,
    columns=[
        Column("verified_at", "Verified", DT),
        Column("lab_number", "Lab no."),
        Column("patient_name", "Patient"),
        Column("test", "Test"),
        Column("specimen", "Specimen"),
        Column("organism", "Organism"),
        Column("resistant", "Resistant"),
        Column("sensitive", "Sensitive", default_visible=False),
    ],
)


async def _culture(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    rows = []
    for item, request, patient in await _verified_items(session, date_from, date_to, culture=True):
        culture = item.culture or {}
        base = {"verified_at": to_local(item.verified_at), "lab_number": request.lab_number,
                "patient_name": patient.name, "test": item.name, "specimen": culture.get("specimen") or ""}
        if culture.get("growth") == "no_growth" or not culture.get("isolates"):
            rows.append({**base, "organism": "No growth", "resistant": "", "sensitive": ""})
            continue
        for isolate in culture["isolates"]:
            panel = isolate.get("antibiotics") or []
            rows.append({
                **base,
                "organism": isolate.get("organism") or "",
                "resistant": ", ".join(row["name"] for row in panel if row.get("result") == "R"),
                "sensitive": ", ".join(row["name"] for row in panel
                                       if row.get("result") in SUSCEPTIBILITY and row.get("result") != "R"),
            })
    return rows


# ------------------------------------------------------------------ billing
BILLING = ReportSpec(
    key="lab-billing",
    title="Lab billing",
    description="What each lab request was billed, on a counter bill or to the admission, and what is paid.",
    columns=[
        Column("registered_at", "Registered", DT),
        Column("lab_number", "Lab no."),
        Column("patient_name", "Patient"),
        Column("tests", "Tests", default_visible=False),
        Column("billing", "Billed to", S),
        Column("invoice_number", "Bill no."),
        Column("amount_paise", "Amount", M, total=True),
        Column("paid_paise", "Paid", M, total=True),
        Column("balance_paise", "Balance", M, total=True),
        Column("status", "Status", S),
    ],
)


async def _billing(session: AsyncSession, *, date_from: date, date_to: date, **_: Any) -> List[Dict[str, Any]]:
    rows = []
    for request, patient, admission in await _requests(session, date_from, date_to):
        live = [item for item in request.items if item.status != "cancelled"]
        invoice = await session.get(Invoice, request.invoice_id) if request.invoice_id else None
        if request.billing == "invoice" and invoice is not None:
            cancelled = invoice.status is InvoiceStatus.CANCELLED
            amount = 0 if cancelled else invoice.total_paise
            paid = 0 if cancelled else invoice.paid_paise
            number = invoice.invoice_number
        else:
            amount = sum(item.unit_rate_paise for item in live) if request.billing == "ipd" else 0
            paid = 0
            number = admission.ip_number if request.billing == "ipd" and admission else ""
        rows.append({
            "registered_at": to_local(request.created_at),
            "lab_number": request.lab_number,
            "patient_name": patient.name,
            "tests": ", ".join(item.name for item in live),
            "billing": request.billing,
            "invoice_number": number,
            "amount_paise": amount,
            "paid_paise": paid,
            "balance_paise": amount - paid if request.billing == "invoice" else 0,
            "status": request.status,
        })
    return rows


register(LAB_REGISTER, _lab_register)
register(TEST_WISE, _test_wise)
register(PENDING, _pending)
register(TURNAROUND, _turnaround)
register(CRITICAL, _critical)
register(CULTURE, _culture)
register(BILLING, _billing)
