"""Investigation ordering and report processing.

Report pipeline for one upload:
    store bytes -> extract text -> classify the document -> read it the way
    that kind of document is read -> AI narrative, for laboratory reports only

Each stage is guarded: a failure downgrades the result rather than losing the
file. A report whose text cannot be read is still stored, still versioned, and
still visible to the doctor — it simply carries no analysis.

Which analyser runs is decided in `app/investigations/reading.py`, and it can
decline. A document that cannot be read confidently is marked unclear and the
doctor is told to open the original, because the alternative — a prescription
put through the laboratory parser — produces flagged abnormal results out of
dose instructions.
"""
import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipeline.base_service import StageError
from app.ai.pipeline.report_summary import ReportSummaryService
from app.core.config import settings
from app.core.logging import get_logger
from app.core.uploads import sanitize_filename, validate_upload
from app.investigations import catalog
from app.investigations.extraction import extract
from app.investigations.reading import read_document
from app.models.enums import (
    Department,
    DocumentKind,
    InvestigationPriority,
    OrderStatus,
    ReportStatus,
)
from app.models.investigation import (
    InvestigationOrder,
    InvestigationOrderItem,
    InvestigationReport,
    InvestigationTemplate,
)
from app.models.patient import Patient
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.investigation_repository import (
    InvestigationOrderRepository,
    InvestigationPreferenceRepository,
    InvestigationReportRepository,
)
from app.repositories.patient_repository import PatientRepository

logger = get_logger(__name__)

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png", "image/jpeg", "image/jpg", "image/tiff", "image/bmp", "image/webp",
    "text/plain", "text/csv",
}
ALLOWED_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".csv",
}


async def mark_order_item_reported(session: AsyncSession, order_item_id: uuid.UUID) -> None:
    """A reported test completes its order item, and perhaps its whole order.

    Shared by signed radiology reports and verified lab results, so both
    decide an order's status in the same way.
    """
    from sqlalchemy import select as _select

    item = await session.get(InvestigationOrderItem, order_item_id)
    if item is None:
        return
    item.reported = True
    await session.flush()
    order = await session.get(InvestigationOrder, item.order_id)
    if order is None or order.status == OrderStatus.CANCELLED:
        return
    siblings = list((await session.execute(
        _select(InvestigationOrderItem).where(InvestigationOrderItem.order_id == order.id)
    )).scalars())
    order.status = (
        OrderStatus.COMPLETED if all(entry.reported for entry in siblings)
        else OrderStatus.PARTIALLY_REPORTED
    )


class InvestigationError(Exception):
    pass


class InvestigationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = InvestigationOrderRepository(session)
        self.reports = InvestigationReportRepository(session)
        self.preferences = InvestigationPreferenceRepository(session)
        self.patients = PatientRepository(session)
        self.consultations = ConsultationRepository(session)
        self.summarizer = ReportSummaryService()

    # ------------------------------------------------------------- ordering
    async def create_order(
        self,
        *,
        patient_id: uuid.UUID,
        consultation_id: Optional[uuid.UUID],
        department: Department,
        codes: List[str],
        priority: InvestigationPriority,
        clinical_notes: Optional[str],
        provisional_diagnosis: Optional[str],
        doctor_id: uuid.UUID,
        doctor_name: str,
        item_instructions: Optional[Dict[str, str]] = None,
    ) -> InvestigationOrder:
        resolved = catalog.expand_codes(codes)
        if not resolved:
            raise InvestigationError("No valid investigations were selected.")

        patient = await self.patients.get(patient_id)
        if patient is None:
            raise InvestigationError("Patient not found.")

        order = InvestigationOrder(
            patient_id=patient_id,
            consultation_id=consultation_id,
            department=department,
            ordered_by_id=doctor_id,
            ordered_by_name=doctor_name,
            priority=priority,
            clinical_notes=clinical_notes,
            provisional_diagnosis=provisional_diagnosis,
            status=OrderStatus.ISSUED,
            issued_at=datetime.now(timezone.utc),
        )
        self.session.add(order)
        await self.session.flush()

        instructions = item_instructions or {}
        for position, item in enumerate(resolved):
            self.session.add(
                InvestigationOrderItem(
                    order_id=order.id,
                    code=item.code,
                    name=item.name,
                    category=item.category,
                    specimen_or_site=item.specimen_or_site,
                    preparation=item.preparation,
                    instructions=instructions.get(item.code),
                    position=position,
                )
            )
        await self.session.commit()
        logger.info(
            "investigation_order_created",
            extra={
                "order_id": str(order.id),
                "patient_id": str(patient_id),
                "count": len(resolved),
                "doctor": doctor_name,
            },
        )
        return await self.orders.get_with_items(order.id)

    async def cancel_order(self, order_id: uuid.UUID) -> Optional[InvestigationOrder]:
        order = await self.orders.get_with_items(order_id)
        if order is None:
            return None
        order.status = OrderStatus.CANCELLED
        await self.session.commit()
        return order

    async def list_orders(
        self, *, patient_id: Optional[uuid.UUID], consultation_id: Optional[uuid.UUID]
    ) -> List[InvestigationOrder]:
        return await self.orders.list_for(
            patient_id=patient_id, consultation_id=consultation_id
        )

    async def get_order(self, order_id: uuid.UUID) -> Optional[InvestigationOrder]:
        return await self.orders.get_with_items(order_id)

    # ---------------------------------------------------- doctor preferences
    async def workspace(self, *, user_id: uuid.UUID, department: Optional[Department]) -> Dict[str, Any]:
        """Everything the picker needs in one round trip."""
        favorites = await self.preferences.favorites(user_id)
        recent = await self.orders.recently_used_codes(user_id=user_id)
        templates = await self.preferences.templates(user_id, department)
        return {
            "favorites": favorites,
            "recent": [
                {"code": code, "name": name, "uses": uses} for code, name, uses in recent
            ],
            "templates": templates,
        }

    async def set_favorite(self, *, user_id: uuid.UUID, code: str, favorite: bool) -> List[str]:
        if catalog.get(code) is None:
            raise InvestigationError(f"Unknown investigation code: {code}")
        if favorite:
            await self.preferences.add_favorite(user_id, code)
        else:
            await self.preferences.remove_favorite(user_id, code)
        await self.session.commit()
        return await self.preferences.favorites(user_id)

    async def create_template(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
        codes: List[str],
        description: Optional[str],
        department: Optional[Department],
        shared: bool,
    ) -> InvestigationTemplate:
        valid = [code for code in codes if catalog.get(code) or code in catalog.PANELS_BY_CODE]
        if not valid:
            raise InvestigationError("A template needs at least one valid investigation.")
        template = InvestigationTemplate(
            user_id=None if shared else user_id,
            department=department,
            name=name.strip(),
            description=description,
            codes=valid,
        )
        await self.preferences.create_template(template)
        await self.session.commit()
        return template

    async def delete_template(self, template_id: uuid.UUID, *, user_id: uuid.UUID) -> bool:
        template = await self.preferences.get_template(template_id)
        if template is None:
            return False
        if template.user_id is not None and template.user_id != user_id:
            raise InvestigationError("You can only delete your own templates.")
        await self.preferences.delete_template(template)
        await self.session.commit()
        return True

    # ----------------------------------------------------------- report file
    @staticmethod
    def storage_path(stored_filename: str) -> Path:
        return Path(settings.MEDIA_ROOT) / "reports" / stored_filename

    @staticmethod
    def _validate_upload(filename: str, content_type: str, data: bytes) -> str:
        """Validate by content, not by the client's claims.

        The Content-Type header and the file extension are both attacker
        controlled, so the leading bytes decide what a file really is. Returns
        the detected media type.
        """
        result = validate_upload(
            data=data,
            filename=filename,
            declared_type=content_type,
            allowed_types=ALLOWED_CONTENT_TYPES,
            max_bytes=settings.MAX_REPORT_UPLOAD_MB * 1024 * 1024,
        )
        if not result.ok:
            raise InvestigationError(result.reason or "This file could not be accepted.")
        return result.detected_type or content_type

    async def upload_report(
        self,
        *,
        patient_id: uuid.UUID,
        consultation_id: Optional[uuid.UUID],
        order_id: Optional[uuid.UUID],
        replaces_id: Optional[uuid.UUID],
        revision_note: Optional[str],
        title: str,
        filename: str,
        content_type: str,
        data: bytes,
        uploaded_by_id: Optional[uuid.UUID],
        uploaded_by_name: str,
        department: Department,
        document_kind: Optional[DocumentKind] = None,
    ) -> InvestigationReport:
        safe_filename = sanitize_filename(filename, fallback='report')
        detected_type = self._validate_upload(safe_filename, content_type, data)

        patient = await self.patients.get(patient_id)
        if patient is None:
            raise InvestigationError("Patient not found.")

        checksum = hashlib.sha256(data).hexdigest()

        # --- version chain -------------------------------------------------
        group_id = uuid.uuid4()
        version = 1
        predecessor: Optional[InvestigationReport] = None
        if replaces_id is not None:
            predecessor = await self.reports.get(replaces_id)
            if predecessor is None:
                raise InvestigationError("The report being replaced no longer exists.")
            if predecessor.patient_id != patient_id:
                raise InvestigationError("A report can only be revised for the same patient.")
            latest = await self.reports.latest_in_group(predecessor.group_id)
            group_id = predecessor.group_id
            version = (latest.version if latest else predecessor.version) + 1
        else:
            duplicate = await self.reports.find_duplicate(patient_id, checksum)
            if duplicate is not None and duplicate.status != ReportStatus.SUPERSEDED:
                raise InvestigationError(
                    "This exact file has already been uploaded for this patient "
                    f"(version {duplicate.version}). Upload it as a revision if it is a corrected copy."
                )

        report_id = uuid.uuid4()
        suffix = Path(safe_filename).suffix.lower() or ".bin"
        stored_filename = f"{report_id}{suffix}"
        destination = self.storage_path(stored_filename)
        try:
            # Disk writes are offloaded so a 25 MB upload cannot stall the
            # event loop for every other request on this worker.
            await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(destination.write_bytes, data)
        except OSError as exc:
            logger.exception("report_write_failed", extra={"report_id": str(report_id)})
            raise InvestigationError("The report file could not be stored on the server.") from exc

        report = InvestigationReport(
            id=report_id,
            patient_id=patient_id,
            consultation_id=consultation_id,
            order_id=order_id,
            group_id=group_id,
            version=version,
            replaces_id=replaces_id,
            revision_note=revision_note,
            title=(title or Path(safe_filename).stem or "Report")[:255],
            original_filename=safe_filename[:512],
            stored_filename=stored_filename,
            content_type=detected_type,
            size_bytes=len(data),
            checksum_sha256=checksum,
            document_kind=document_kind,
            status=ReportStatus.UPLOADED,
            uploaded_by_id=uploaded_by_id,
            uploaded_by_name=uploaded_by_name,
        )
        self.session.add(report)

        if predecessor is not None:
            predecessor.status = ReportStatus.SUPERSEDED
        await self.session.commit()

        await self.process_report(report.id, patient=patient, department=department)
        return await self.reports.get(report.id)

    # -------------------------------------------------------- report analysis
    async def process_report(
        self,
        report_id: uuid.UUID,
        *,
        patient: Optional[Patient] = None,
        department: Department = Department.ORTHOPEDICS,
    ) -> Optional[InvestigationReport]:
        """Extract, evaluate and summarise. Safe to re-run."""
        report = await self.reports.get(report_id)
        if report is None:
            return None
        if patient is None:
            patient = await self.patients.get(report.patient_id)

        report.status = ReportStatus.EXTRACTING
        await self.session.flush()

        path = self.storage_path(report.stored_filename)
        try:
            data = await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            report.status = ReportStatus.FAILED
            report.error_detail = f"Stored file could not be read: {exc}"
            await self.session.commit()
            return report

        extraction = extract(data, report.content_type, report.original_filename)
        report.extracted_text = extraction.text or None
        report.extraction_method = extraction.method
        report.page_count = extraction.page_count

        if not extraction.ok:
            report.status = ReportStatus.FAILED
            report.error_detail = extraction.warning or "No readable text was found in this file."
            # Shaped like every other unclear result, so the doctor sees the
            # same card here as anywhere else nothing could be read.
            report.analysis = {
                "extraction": {"method": extraction.method, "warning": extraction.warning},
                "document_kind": report.document_kind.value if report.document_kind else None,
                "declared_kind": report.document_kind.value if report.document_kind else None,
                "detected_kind": None,
                "clarity": "unclear",
                "unclear_reason": (
                    extraction.warning
                    or "No text at all could be read from this file."
                ),
                "results": [],
                "abnormal": [],
                "critical": [],
                "abnormal_count": 0,
                "critical_count": 0,
            }
            await self.session.commit()
            logger.info(
                "report_extraction_empty",
                extra={"report_id": str(report_id), "method": extraction.method},
            )
            return report

        # --- classify, then read it the way that kind is read ---------------
        # A handwritten prescription does not come back from OCR as an error;
        # it comes back as confident-looking rubbish. Everything that decides
        # whether this document may be believed happens in `read_document`,
        # which is allowed to answer "unclear".
        reading = read_document(
            extraction.text,
            declared=report.document_kind,
            extraction={
                "method": extraction.method,
                "page_count": extraction.page_count,
                "warning": extraction.warning,
                "characters": len(extraction.text),
                "legible": extraction.legible,
            },
            legible=extraction.legible,
            sex=patient.gender if patient else None,
            age=patient.age if patient else None,
        )
        analysis: Dict[str, Any] = reading.analysis

        if not reading.should_summarise:
            report.analysis = analysis
            report.status = ReportStatus.ANALYZED
            report.error_detail = None
            await self.session.commit()
            logger.info(
                "report_read_without_summary",
                extra={
                    "report_id": str(report_id),
                    "kind": analysis.get("document_kind"),
                    "clarity": analysis.get("clarity"),
                },
            )
            return report

        # --- narrative pass, laboratory reports only (advisory) -------------
        previous_summary = None
        if report.version > 1:
            history = await self.reports.version_history(report.group_id)
            for older in history:
                if older.id != report.id and older.analysis:
                    previous_summary = (older.analysis or {}).get("summary")
                    break

        try:
            summary = await self.summarizer.summarize(
                patient={
                    "age": patient.age if patient else None,
                    "gender": patient.gender.value if patient else None,
                },
                department=department.value,
                analysis={
                    "results": analysis["results"],
                    "abnormal_count": analysis["abnormal_count"],
                    "critical_count": analysis["critical_count"],
                    "narrative_lines": analysis.get("narrative_lines", []),
                },
                raw_text_excerpt=extraction.text,
                previous_summary=previous_summary,
                tag=str(report_id),
            )
            analysis["summary"] = summary.model_dump()
        except StageError as exc:
            logger.exception("report_summary_failed", extra={"report_id": str(report_id)})
            analysis["summary_error"] = str(exc)

        report.analysis = analysis
        report.status = ReportStatus.ANALYZED
        report.error_detail = None

        # Mark matching order items as reported.
        if report.order_id:
            order = await self.orders.get_with_items(report.order_id)
            if order is not None:
                matched_keys = {
                    result.get("analyte_key")
                    for result in analysis["results"]
                    if result.get("analyte_key")
                }
                for item in order.items:
                    entry = catalog.get(item.code)
                    if entry and entry.analytes and matched_keys.intersection(entry.analytes):
                        item.reported = True
                await self.session.flush()
                await self.orders.mark_items_reported(order.id)

        await self.session.commit()
        logger.info(
            "report_analyzed",
            extra={
                "report_id": str(report_id),
                "method": extraction.method,
                "kind": analysis.get("document_kind"),
                "results": len(analysis["results"]),
                "abnormal": analysis["abnormal_count"],
                "critical": analysis["critical_count"],
            },
        )
        return report

    # ------------------------------------------------------------- retrieval
    async def get_report(self, report_id: uuid.UUID) -> Optional[InvestigationReport]:
        return await self.reports.get(report_id)

    async def list_reports(
        self,
        *,
        patient_id: Optional[uuid.UUID],
        consultation_id: Optional[uuid.UUID],
        include_superseded: bool = False,
    ) -> List[InvestigationReport]:
        if consultation_id is not None:
            return await self.reports.list_for_consultation(
                consultation_id, current_only=not include_superseded
            )
        if patient_id is not None:
            return await self.reports.list_for_patient(
                patient_id, current_only=not include_superseded
            )
        return []

    async def version_history(self, report_id: uuid.UUID) -> Tuple[Optional[InvestigationReport], List[InvestigationReport]]:
        report = await self.reports.get(report_id)
        if report is None:
            return None, []
        return report, await self.reports.version_history(report.group_id)
