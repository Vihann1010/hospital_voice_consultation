"""The surgical register.

Every case booked for theatre, in the order it was scheduled, with its team,
its side and its theatre times. The book an OT in-charge keeps and an auditor
asks for. Cancelled cases stay in the register with their reason, because a
case that did not happen still needs accounting for.

A clinical report, not a financial one: it carries no money, and is open to
anyone who can read a patient's record.
"""
from datetime import date
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import day_bounds, to_local
from app.models.ipd import Admission
from app.models.patient import Patient
from app.models.theatre import Surgery
from app.reports.definitions import Column, ColumnType, ReportSpec, register
from app.theatre import rules

T = ColumnType.TEXT
N = ColumnType.NUMBER
DT = ColumnType.DATETIME

SURGICAL_REGISTER = ReportSpec(
    key="surgical-register",
    title="Surgical register",
    description="Every case booked for theatre, with its team, side and theatre times.",
    permission="patient:read",
    columns=[
        Column("scheduled_at", "Scheduled", DT),
        Column("ot_number", "OT number"),
        Column("patient_name", "Patient"),
        Column("uhid", "UHID", default_visible=False),
        Column("ip_number", "IP number"),
        Column("operation", "Operation"),
        Column("laterality", "Side"),
        Column("surgeon", "Surgeon"),
        Column("assistants", "Assistants", default_visible=False),
        Column("anaesthetist", "Anaesthetist"),
        Column("anaesthesia", "Anaesthesia"),
        Column("room", "Theatre", default_visible=False),
        Column("priority", "Priority", ColumnType.STATUS),
        Column("wheel_in_at", "In", DT),
        Column("wheel_out_at", "Out", DT),
        Column("theatre_minutes", "Theatre min", N, total=True),
        Column("surgery_minutes", "Surgery min", N, total=True, default_visible=False),
        Column("status", "Status", ColumnType.STATUS),
        Column("remarks", "Remarks", default_visible=False),
    ],
)


async def _surgical_register(
    session: AsyncSession, *, date_from: date, date_to: date, **_: Any
) -> List[Dict[str, Any]]:
    start, _end = day_bounds(date_from)
    _start, end = day_bounds(date_to)
    result = await session.execute(
        select(Surgery, Patient, Admission)
        .join(Patient, Patient.id == Surgery.patient_id)
        .outerjoin(Admission, Admission.id == Surgery.admission_id)
        .where(Surgery.scheduled_at >= start, Surgery.scheduled_at < end)
        .order_by(Surgery.scheduled_at)
    )
    rows = []
    for surgery, patient, admission in result.all():
        spans = rules.durations(surgery.times())
        rows.append({
            "scheduled_at": to_local(surgery.scheduled_at),
            "ot_number": surgery.ot_number,
            "patient_name": patient.name,
            "uhid": patient.uhid or "",
            "ip_number": admission.ip_number if admission else "",
            "operation": surgery.operation_name,
            "laterality": surgery.laterality,
            "surgeon": surgery.surgeon_name,
            "assistants": ", ".join(surgery.assistants or []),
            "anaesthetist": surgery.anaesthetist_name or "",
            "anaesthesia": surgery.anaesthesia_type or "",
            "room": surgery.room_name or "",
            "priority": surgery.priority,
            "wheel_in_at": to_local(surgery.wheel_in_at) if surgery.wheel_in_at else None,
            "wheel_out_at": to_local(surgery.wheel_out_at) if surgery.wheel_out_at else None,
            "theatre_minutes": spans["theatre_minutes"] or 0,
            "surgery_minutes": spans["surgery_minutes"] or 0,
            "status": surgery.status.value,
            "remarks": surgery.cancel_reason or surgery.notes or "",
        })
    return rows


register(SURGICAL_REGISTER, _surgical_register)
