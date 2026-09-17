"""The medical records bundle for one admission.

A checklist first: every document the hospital holds for the stay, in the
order the records room files it, with what is missing called out rather than
silently absent — an admission with no signed discharge summary should say so
on the screen that is about to print the file.

Then the build: the chosen documents rendered one by one, bound behind a
cover and a contents page that gives each document's first page. It runs in
the background and reports progress, because an admission with a fortnight of
notes, charts and scans takes long enough that a spinner with no count looks
broken.

Unsigned documents are left unticked on the checklist, and print stamped
DRAFT if chosen. Superseded versions and withdrawn files never appear.
Printing a bundle does not count as printing the documents in it: a
discharge summary bound into the file is not a duplicate handed to anyone.
"""
import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.clock import to_local
from app.core.logging import get_logger
from app.models.enums import AdmissionStatus, PadStatus, PatientFileCategory, ReportStatus
from app.pads.defaults import document_type as type_spec

logger = get_logger(__name__)

SECTIONS = [
    "Admission record", "Consent", "Doctor's notes", "Nursing", "Theatre", "Investigations",
    "Charts", "Certificates", "Discharge", "Attachments", "Billing",
]
_PAD_SECTION = {
    "ipd_admission_note": "Doctor's notes",
    "ipd_progress_note": "Doctor's notes",
    "ipd_nursing_assessment": "Nursing",
    "ipd_nursing_note": "Nursing",
    "ipd_discharge_summary": "Discharge",
}
PRINTABLE_IMAGES = {"image/png", "image/jpeg", "image/jpg", "image/tiff", "image/bmp", "image/webp"}
JOB_TTL = timedelta(minutes=30)


@dataclass
class Item:
    key: str
    section: str
    title: str
    kind: str
    on: Optional[str] = None          # ISO local date the document belongs to
    status: str = "ready"
    included: bool = True
    note: Optional[str] = None


def section_for(document_type: str) -> str:
    spec = type_spec(document_type)
    if spec is not None and spec.family == "consent":
        return "Consent"
    if spec is not None and spec.family == "certificate":
        return "Certificates"
    if spec is not None and spec.family == "radiology":
        return "Investigations"
    if document_type.startswith("ot_"):
        return "Theatre"
    return _PAD_SECTION.get(document_type, "Doctor's notes")


def sort_key(item: Item) -> Tuple[int, str, str]:
    return (SECTIONS.index(item.section) if item.section in SECTIONS else len(SECTIONS), item.on or "", item.title)


def in_range(on: Optional[str], date_from: Optional[date], date_to: Optional[date]) -> bool:
    if not on:
        return True
    day = date.fromisoformat(on)
    return (date_from is None or day >= date_from) and (date_to is None or day <= date_to)


def _day(moment: Optional[datetime]) -> Optional[str]:
    return to_local(moment).date().isoformat() if moment else None


# ------------------------------------------------------------- checklist
async def checklist(session, admission_id: uuid.UUID) -> Dict[str, Any]:
    from app.models.emr import Invoice  # noqa: F401  (imported for the relationship)
    from app.models.investigation import InvestigationReport
    from app.models.ipd import Admission, MedicationOrder, VitalsRecord
    from app.models.pad import PadDocument
    from app.models.patient import Patient
    from app.models.patient_file import PatientFile
    from app.models.theatre import Surgery

    admission = await session.get(Admission, admission_id)
    if admission is None:
        raise LookupError("Admission not found.")
    patient = await session.get(Patient, admission.patient_id)
    stay_end = admission.discharged_at or datetime.now(timezone.utc)
    items: List[Item] = [Item("cover", "Admission record", "Admission record (cover sheet)", "cover",
                              _day(admission.admitted_at))]

    surgeries = list((await session.execute(
        select(Surgery).where(Surgery.admission_id == admission.id).order_by(Surgery.scheduled_at)
    )).scalars())
    for case in surgeries:
        if case.status.value == "cancelled":
            continue
        items.append(Item(f"slip:{case.id}", "Theatre", f"Surgery slip — {case.ot_number} {case.operation_name}",
                          "slip", _day(case.scheduled_at)))

    documents = list((await session.execute(
        select(PadDocument).where(
            PadDocument.status != PadStatus.SUPERSEDED,
            or_(
                PadDocument.admission_id == admission.id,
                PadDocument.surgery_id.in_([case.id for case in surgeries]) if surgeries else False,
                (PadDocument.patient_id == patient.id) & (PadDocument.document_type == "radiology_report")
                & (PadDocument.created_at >= admission.admitted_at) & (PadDocument.created_at <= stay_end),
            ),
        ).order_by(PadDocument.created_at)
    )).scalars())
    consent_ids = set()
    for document in documents:
        spec = type_spec(document.document_type)
        if spec is None or document.document_type == "opd_visit":
            continue
        signed = document.status == PadStatus.SIGNED
        title = document.title + (f" — {document.serial_number}" if document.serial_number else "")
        if spec.many and not spec.family:
            title += f" ({_day(document.signed_at or document.created_at)})"
        note = None if signed else "Not signed — prints stamped DRAFT"
        if spec.family == "consent":
            consent_ids.add(document.id)
            if signed and not document.paper_signed_at:
                note = "Patient's signed paper copy not recorded"
        items.append(Item(f"pad:{document.id}", section_for(document.document_type), title, "pad",
                          _day(document.signed_at or document.created_at),
                          "signed" if signed else "draft", included=signed, note=note))

    reports = list((await session.execute(
        select(InvestigationReport).where(
            InvestigationReport.patient_id == patient.id,
            InvestigationReport.status != ReportStatus.SUPERSEDED,
            InvestigationReport.created_at >= admission.admitted_at,
            InvestigationReport.created_at <= stay_end,
        ).order_by(InvestigationReport.created_at)
    )).scalars())
    for report in reports:
        printable = report.content_type == "application/pdf" or report.content_type in PRINTABLE_IMAGES
        items.append(Item(f"report:{report.id}", "Investigations", f"Report — {report.title}", "report",
                          _day(report.created_at), "uploaded", included=printable,
                          note=None if printable else "Not a printable file"))

    from app.models.lab import LabRequest

    lab_requests = list((await session.execute(
        select(LabRequest).options(selectinload(LabRequest.items)).where(
            LabRequest.patient_id == patient.id,
            LabRequest.status != "cancelled",
            or_(
                LabRequest.admission_id == admission.id,
                (LabRequest.created_at >= admission.admitted_at) & (LabRequest.created_at <= stay_end),
            ),
        ).order_by(LabRequest.created_at)
    )).scalars())
    for lab in lab_requests:
        live = [entry for entry in lab.items if entry.status != "cancelled"]
        verified = [entry for entry in live if entry.status == "verified"]
        if verified and len(verified) == len(live):
            state, note = "verified", None
        elif verified:
            state, note = "partial", f"{len(live) - len(verified)} test(s) not verified yet; they print as pending"
        else:
            state, note = "pending", "No result verified yet"
        names = ", ".join(entry.name for entry in live)
        items.append(Item(f"lab:{lab.id}", "Investigations",
                          f"Lab report — {lab.lab_number} ({names[:100]}{'...' if len(names) > 100 else ''})",
                          "lab", _day(lab.created_at), state, included=bool(verified), note=note))

    if (await session.execute(select(VitalsRecord.id).where(VitalsRecord.admission_id == admission.id).limit(1))).first():
        items.append(Item("vitals", "Charts", "Vitals chart", "vitals", _day(admission.admitted_at)))
    if (await session.execute(select(MedicationOrder.id).where(MedicationOrder.admission_id == admission.id).limit(1))).first():
        items.append(Item("mar", "Charts", "Drug administration record", "mar", _day(admission.admitted_at)))

    files = list((await session.execute(
        select(PatientFile).where(
            PatientFile.withdrawn_at.is_(None),
            or_(PatientFile.admission_id == admission.id,
                PatientFile.pad_document_id.in_(consent_ids) if consent_ids else False),
        ).order_by(PatientFile.created_at)
    )).scalars())
    for record in files:
        section = "Consent" if record.category == PatientFileCategory.SIGNED_CONSENT else "Attachments"
        items.append(Item(f"file:{record.id}", section, record.title, "file",
                          _day(record.created_at) if record.document_date is None else record.document_date.isoformat(),
                          "uploaded"))

    if admission.final_invoice_id:
        items.append(Item(f"invoice:{admission.final_invoice_id}", "Billing", "Final bill", "invoice",
                          _day(admission.discharged_at)))

    signed_types = {d.document_type for d in documents if d.status == PadStatus.SIGNED}
    missing = []
    if "ipd_admission_note" not in signed_types:
        missing.append("No signed admission note")
    if "ipd_nursing_assessment" not in signed_types:
        missing.append("No signed nursing initial assessment")
    if "consent_general" not in signed_types:
        missing.append("No signed general consent")
    if admission.status == AdmissionStatus.DISCHARGED and "ipd_discharge_summary" not in signed_types:
        missing.append("No signed discharge summary")
    for case in surgeries:
        if case.status.value == "cancelled":
            continue
        case_types = {d.document_type for d in documents if d.surgery_id == case.id and d.status == PadStatus.SIGNED}
        if "ot_operation_note" not in case_types and case.status.value == "completed":
            missing.append(f"No signed operation note for {case.ot_number}")
        has_consent = any(d.document_type == "consent_surgical" and d.surgery_id == case.id
                          and d.status == PadStatus.SIGNED for d in documents)
        if not has_consent:
            missing.append(f"No signed surgical consent for {case.ot_number}")

    items.sort(key=sort_key)
    return {
        "admission": {
            "id": admission.id, "ip_number": admission.ip_number, "status": admission.status.value,
            "admitted_on": _day(admission.admitted_at), "discharged_on": _day(admission.discharged_at),
            "patient_name": patient.name, "uhid": patient.uhid,
        },
        "items": [asdict(item) for item in items],
        "missing": missing,
    }


# ----------------------------------------------------------------- render
async def _render(session, item: Dict[str, Any], *, admission, patient, date_from, date_to) -> bytes:
    from app.billing.pdf import render_invoice_pdf
    from app.models.consultant import Consultant
    from app.models.emr import Invoice
    from app.models.investigation import InvestigationReport
    from app.models.ipd import BedOccupancy, MedicationOrder, VitalsRecord
    from app.models.pad import PadDocument
    from app.models.patient_file import PatientFile
    from app.models.theatre import Surgery
    from app.mrd import charts_pdf
    from app.pads.forms_pdf import render_form_pdf
    from app.pads.pdf import render_pad_pdf
    from app.printing.layout import load_layout
    from app.services.investigation_service import InvestigationService
    from app.services.patient_file_service import PatientFileService
    from app.theatre.slip_pdf import render_surgery_slip

    kind, _, ref = item["key"].partition(":")
    ref_id = uuid.UUID(ref) if ref else None

    if kind == "cover":
        occupancies = list((await session.execute(
            select(BedOccupancy).where(BedOccupancy.admission_id == admission.id).order_by(BedOccupancy.started_at)
        )).scalars())
        surgeries = list((await session.execute(
            select(Surgery).where(Surgery.admission_id == admission.id).order_by(Surgery.scheduled_at)
        )).scalars())
        attendant = " · ".join(p for p in (admission.attendant_name, admission.attendant_relation,
                                           admission.attendant_phone) if p) or None
        return await asyncio.to_thread(charts_pdf.render_cover_pdf, admission=admission, patient=patient,
                                       occupancies=occupancies, surgeries=surgeries, attendant=attendant,
                                       layout=await load_layout(session, "ipd_discharge_summary"))
    if kind == "pad":
        document = await session.get(PadDocument, ref_id)
        spec = type_spec(document.document_type)
        layout = await load_layout(session, document.document_type)
        watermark = "DRAFT" if document.status == PadStatus.DRAFT else None
        if spec is not None and spec.family in ("certificate", "consent"):
            doctor = None
            if document.signed_by_id:
                doctor = (await session.execute(
                    select(Consultant).where(Consultant.user_id == document.signed_by_id)
                )).scalar_one_or_none()
            return await asyncio.to_thread(render_form_pdf, document=document, patient=patient, admission=admission,
                                           doctor=doctor, layout=layout, watermark=watermark)
        return await asyncio.to_thread(render_pad_pdf, document=document, patient=patient, layout=layout,
                                       watermark=watermark)
    if kind == "slip":
        case = await session.get(Surgery, ref_id)
        return await asyncio.to_thread(render_surgery_slip, surgery=case, patient=patient, admission=admission,
                                       layout=await load_layout(session, "ot_slip"))
    if kind in ("report", "file"):
        if kind == "report":
            record = await session.get(InvestigationReport, ref_id)
            path = InvestigationService.storage_path(record.stored_filename)
            caption = f"Uploaded by {record.uploaded_by_name} · {to_local(record.created_at):%d %b %Y}"
        else:
            record = await session.get(PatientFile, ref_id)
            path = PatientFileService.storage_path(record.stored_filename)
            caption = f"Attached by {record.uploaded_by_name} · {to_local(record.created_at):%d %b %Y}"
        data = await asyncio.to_thread(Path(path).read_bytes)
        if record.content_type == "application/pdf":
            return data
        return await asyncio.to_thread(charts_pdf.render_image_pdf, data=data, title=record.title,
                                       caption=f"{patient.name} · {admission.ip_number} · {caption}")
    if kind == "vitals":
        records = list((await session.execute(
            select(VitalsRecord).where(VitalsRecord.admission_id == admission.id)
        )).scalars())
        return await asyncio.to_thread(charts_pdf.render_vitals_pdf, admission=admission, patient=patient,
                                       records=records, date_from=date_from, date_to=date_to)
    if kind == "mar":
        orders = list((await session.execute(
            select(MedicationOrder).options(selectinload(MedicationOrder.administrations))
            .where(MedicationOrder.admission_id == admission.id)
        )).scalars())
        return await asyncio.to_thread(charts_pdf.render_mar_pdf, admission=admission, patient=patient,
                                       orders=orders, date_from=date_from, date_to=date_to)
    if kind == "invoice":
        invoice = (await session.execute(
            select(Invoice).options(selectinload(Invoice.lines), selectinload(Invoice.payments))
            .where(Invoice.id == ref_id)
        )).scalar_one()
        return await asyncio.to_thread(render_invoice_pdf, invoice, patient, admission.ip_number,
                                       layout=await load_layout(session, "invoice"))
    if kind == "lab":
        from app.lab.report_pdf import render_lab_report
        from app.models.lab import LabRequest

        lab = (await session.execute(
            select(LabRequest).options(selectinload(LabRequest.items)).where(LabRequest.id == ref_id)
        )).scalar_one()
        return await asyncio.to_thread(render_lab_report, request=lab, items=list(lab.items), patient=patient,
                                       admission=admission, layout=await load_layout(session, "lab_report"))
    raise ValueError(f"Unknown document {item['key']}")


# -------------------------------------------------------------------- jobs
@dataclass
class Job:
    id: str
    admission_id: uuid.UUID
    requested_by: str
    total: int
    done: int = 0
    current: str = ""
    status: str = "running"            # running | done | failed
    error: Optional[str] = None
    pages: int = 0
    skipped: List[Dict[str, str]] = field(default_factory=list)
    pdf: Optional[bytes] = None
    filename: str = "records.pdf"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def public(self) -> Dict[str, Any]:
        return {"job_id": self.id, "admission_id": self.admission_id, "status": self.status,
                "total": self.total, "done": self.done, "current": self.current, "error": self.error,
                "pages": self.pages, "skipped": self.skipped, "ready": self.pdf is not None}


JOBS: Dict[str, Job] = {}


def _prune() -> None:
    cutoff = datetime.now(timezone.utc) - JOB_TTL
    for job_id in [key for key, job in JOBS.items() if job.created_at < cutoff]:
        JOBS.pop(job_id, None)


async def start(session, admission_id: uuid.UUID, *, keys: List[str], date_from: Optional[date],
                date_to: Optional[date], requested_by: str) -> Job:
    from app.db.session import AsyncSessionLocal

    plan = await checklist(session, admission_id)
    known = {item["key"]: item for item in plan["items"]}
    unknown = [key for key in keys if key not in known]
    if unknown:
        raise ValueError("Some chosen documents are not part of this admission's record. Reload the checklist.")
    chosen = [known[key] for key in [item["key"] for item in plan["items"]] if key in set(keys)]
    if not chosen:
        raise ValueError("Choose at least one document.")
    _prune()
    job = Job(id=uuid.uuid4().hex, admission_id=admission_id, requested_by=requested_by, total=len(chosen),
              filename=f"{plan['admission']['ip_number']}-medical-record.pdf")
    JOBS[job.id] = job

    async def run() -> None:
        from pypdf import PdfReader

        from app.models.ipd import Admission
        from app.models.patient import Patient
        from app.mrd import charts_pdf
        from app.printing.layout import merge_pdfs

        try:
            async with AsyncSessionLocal() as work:
                admission = await work.get(Admission, admission_id)
                patient = await work.get(Patient, admission.patient_id)
                parts: List[Tuple[Dict[str, Any], bytes, int]] = []
                cover: Optional[bytes] = None
                for item in chosen:
                    job.current = item["title"]
                    if item["kind"] not in ("cover", "vitals", "mar") and not in_range(item["on"], date_from, date_to):
                        job.skipped.append({"title": item["title"], "reason": "Outside the chosen dates"})
                    else:
                        try:
                            data = await _render(work, item, admission=admission, patient=patient,
                                                 date_from=date_from, date_to=date_to)
                            pages = len(PdfReader(__import__("io").BytesIO(data)).pages)
                            if item["kind"] == "cover":
                                cover = data
                            else:
                                parts.append((item, data, pages))
                        except Exception as exc:  # noqa: BLE001 - one bad file must not sink the bundle
                            logger.exception("mrd_item_failed", extra={"key": item["key"]})
                            job.skipped.append({"title": item["title"],
                                                "reason": "Could not be printed" if not isinstance(exc, FileNotFoundError)
                                                else "The stored file is missing"})
                    job.done += 1

                job.current = "Binding the file"
                cover_pages = len(PdfReader(__import__("io").BytesIO(cover)).pages) if cover else 0
                span = ""
                if date_from or date_to:
                    span = (f"Documents dated {date_from.strftime('%d %b %Y') if date_from else 'from admission'}"
                            f" to {date_to.strftime('%d %b %Y') if date_to else 'today'}")

                def contents(offset: int) -> bytes:
                    entries, page = [], offset
                    for item, _data, count in parts:
                        when = date.fromisoformat(item["on"]).strftime("%d %b %Y") if item["on"] else ""
                        entries.append((item["section"], item["title"], when, page))
                        page += count
                    return charts_pdf.render_contents_pdf(
                        admission=admission, patient=patient, entries=entries,
                        skipped=[(s["title"], s["reason"]) for s in job.skipped],
                        generated_by=job.requested_by, date_range=span)

                # The contents page's own length decides where everything after it starts.
                draft = await asyncio.to_thread(contents, cover_pages + 2)
                contents_pages = len(PdfReader(__import__("io").BytesIO(draft)).pages)
                index = await asyncio.to_thread(contents, cover_pages + contents_pages + 1)
                bound = await asyncio.to_thread(
                    merge_pdfs, [part for part in ([cover] if cover else []) + [index] + [d for _i, d, _c in parts]]
                )
                bound = await asyncio.to_thread(
                    charts_pdf.stamp_file_pages, bound, f"{admission.ip_number} · {patient.name} · medical record"
                )
                job.pages = len(PdfReader(__import__("io").BytesIO(bound)).pages)
                job.pdf = bound
                job.status = "done"
                job.current = ""
        except Exception as exc:  # noqa: BLE001
            logger.exception("mrd_bundle_failed", extra={"job": job.id})
            job.status = "failed"
            job.error = "The records file could not be put together. Try again, or leave out the last document named."

    asyncio.create_task(run())
    return job
