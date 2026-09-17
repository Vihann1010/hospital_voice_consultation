"""Where a bill came from: the OPD counter, an inpatient's final bill, or the lab.

One answer for every report, so the consolidated invoice list, the refund list
and department billing cannot disagree about which desk raised a bill.
"""
import uuid
from typing import Dict, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emr import Invoice
from app.models.ipd import Admission
from app.models.lab import LabRequest

IPD = "IPD"
LAB = "Lab"
OPD = "OPD"
COUNTER = "Counter"


async def invoice_sources(session: AsyncSession, invoices: Iterable[Invoice]) -> Dict[uuid.UUID, str]:
    invoices = list(invoices)
    ids = [invoice.id for invoice in invoices]
    if not ids:
        return {}
    final_bills = {row[0] for row in (await session.execute(
        select(Admission.final_invoice_id).where(Admission.final_invoice_id.in_(ids))
    )).all()}
    lab_bills = {row[0] for row in (await session.execute(
        select(LabRequest.invoice_id).where(LabRequest.invoice_id.in_(ids))
    )).all()}
    # An inpatient's final bill usually carries the OPD visit it came from,
    # so the admission is checked first.
    return {
        invoice.id: IPD if invoice.id in final_bills
        else LAB if invoice.id in lab_bills
        else OPD if invoice.visit_id
        else COUNTER
        for invoice in invoices
    }
