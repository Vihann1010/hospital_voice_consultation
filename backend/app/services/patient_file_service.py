"""Attaching files to a patient's record.

Files are checked by their content, not their name (see app/core/uploads.py),
linked only to a visit, admission or consent form of the same patient, and
refused when the identical file is already on the record. Attaching the
signed scan of a consent form also records that the signed paper copy came
back, so the two can never disagree.
"""
import asyncio
import hashlib
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.uploads import sanitize_filename, validate_upload
from app.models.consultation import Consultation
from app.models.enums import PadStatus, PatientFileCategory
from app.models.ipd import Admission
from app.models.pad import PadDocument
from app.models.patient import Patient
from app.models.patient_file import PatientFile
from app.models.user import User
from app.pads.defaults import document_type as type_spec
from app.services.investigation_service import ALLOWED_CONTENT_TYPES

logger = get_logger(__name__)

CATEGORY_LABEL = {
    PatientFileCategory.IDENTITY_PROOF: "Identity proof",
    PatientFileCategory.REFERRAL_LETTER: "Referral letter",
    PatientFileCategory.PREVIOUS_RECORDS: "Previous records",
    PatientFileCategory.OUTSIDE_INVESTIGATION: "Outside investigation / film",
    PatientFileCategory.SIGNED_CONSENT: "Signed consent form",
    PatientFileCategory.CLINICAL_PHOTOGRAPH: "Clinical photograph",
    PatientFileCategory.INSURANCE: "Insurance / TPA",
    PatientFileCategory.OTHER: "Other",
}

# Text files are for lab exports; a patient's record takes documents and images.
FILE_TYPES = {kind for kind in ALLOWED_CONTENT_TYPES if not kind.startswith("text/")}


class PatientFileError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PatientFileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def storage_path(stored_filename: str) -> Path:
        return Path(settings.MEDIA_ROOT) / "patient_files" / stored_filename

    async def upload(
        self,
        *,
        patient_id: uuid.UUID,
        category: PatientFileCategory,
        title: Optional[str],
        filename: str,
        content_type: str,
        data: bytes,
        user: User,
        consultation_id: Optional[uuid.UUID] = None,
        admission_id: Optional[uuid.UUID] = None,
        pad_document_id: Optional[uuid.UUID] = None,
        document_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> PatientFile:
        safe_name = sanitize_filename(filename, fallback="file")
        check = validate_upload(
            data=data, filename=safe_name, declared_type=content_type,
            allowed_types=FILE_TYPES, max_bytes=settings.MAX_REPORT_UPLOAD_MB * 1024 * 1024,
        )
        if not check.ok:
            raise PatientFileError(check.reason or "This file could not be accepted.")

        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise PatientFileError("Patient not found.", status_code=404)

        for model, linked_id, label in (
            (Consultation, consultation_id, "visit"),
            (Admission, admission_id, "admission"),
        ):
            if linked_id is None:
                continue
            linked = await self.session.get(model, linked_id)
            if linked is None:
                raise PatientFileError(f"That {label} was not found.", status_code=404)
            if linked.patient_id != patient.id:
                raise PatientFileError(f"That {label} belongs to another patient.")

        consent: Optional[PadDocument] = None
        if pad_document_id is not None:
            consent = (
                await self.session.execute(
                    select(PadDocument).where(PadDocument.id == pad_document_id).with_for_update()
                )
            ).scalar_one_or_none()
            spec = type_spec(consent.document_type) if consent else None
            if consent is None or spec is None or spec.family != "consent":
                raise PatientFileError("A scan can only be attached to a consent form.")
            if consent.patient_id != patient.id:
                raise PatientFileError("That consent form belongs to another patient.")
            if consent.status != PadStatus.SIGNED:
                raise PatientFileError(
                    "Attach the patient's signed copy to the current signed version of the form.",
                    status_code=409,
                )
            category = PatientFileCategory.SIGNED_CONSENT
            admission_id = admission_id or consent.admission_id
            consultation_id = consultation_id or consent.consultation_id

        checksum = hashlib.sha256(data).hexdigest()
        duplicate = (
            await self.session.execute(
                select(PatientFile).where(
                    PatientFile.patient_id == patient.id,
                    PatientFile.checksum_sha256 == checksum,
                    PatientFile.withdrawn_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise PatientFileError(
                f"This exact file is already on the patient's record, as \"{duplicate.title}\".",
                status_code=409,
            )

        file_id = uuid.uuid4()
        stored = f"{file_id}{Path(safe_name).suffix.lower() or '.bin'}"
        destination = self.storage_path(stored)
        try:
            await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(destination.write_bytes, data)
        except OSError as exc:
            logger.exception("patient_file_write_failed", extra={"file_id": str(file_id)})
            raise PatientFileError("The file could not be stored on the server.", status_code=500) from exc

        record = PatientFile(
            id=file_id,
            patient_id=patient.id,
            consultation_id=consultation_id,
            admission_id=admission_id,
            pad_document_id=consent.id if consent else None,
            category=category,
            title=(title or "").strip()[:255] or (
                f"Signed {consent.title.lower()}" if consent else Path(safe_name).stem or "File"
            )[:255],
            document_date=document_date,
            notes=(notes or "").strip() or None,
            original_filename=safe_name[:512],
            stored_filename=stored,
            content_type=check.detected_type or content_type,
            size_bytes=len(data),
            checksum_sha256=checksum,
            uploaded_by_id=user.id,
            uploaded_by_name=user.full_name,
        )
        self.session.add(record)
        if consent is not None and consent.paper_signed_at is None:
            consent.paper_signed_at = _now()
            consent.paper_signed_by_name = user.full_name
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get(self, file_id: uuid.UUID) -> PatientFile:
        record = await self.session.get(PatientFile, file_id)
        if record is None:
            raise PatientFileError("That file was not found.", status_code=404)
        return record

    async def list(
        self,
        *,
        patient_id: uuid.UUID,
        admission_id: Optional[uuid.UUID] = None,
        consultation_id: Optional[uuid.UUID] = None,
        pad_document_id: Optional[uuid.UUID] = None,
        category: Optional[PatientFileCategory] = None,
        include_withdrawn: bool = False,
    ) -> List[PatientFile]:
        statement = select(PatientFile).where(PatientFile.patient_id == patient_id)
        if admission_id is not None:
            statement = statement.where(PatientFile.admission_id == admission_id)
        if consultation_id is not None:
            statement = statement.where(PatientFile.consultation_id == consultation_id)
        if pad_document_id is not None:
            statement = statement.where(PatientFile.pad_document_id == pad_document_id)
        if category is not None:
            statement = statement.where(PatientFile.category == category)
        if not include_withdrawn:
            statement = statement.where(PatientFile.withdrawn_at.is_(None))
        statement = statement.order_by(PatientFile.created_at.desc())
        return list((await self.session.execute(statement)).scalars())

    async def withdraw(self, file_id: uuid.UUID, *, reason: str, user: User) -> PatientFile:
        record = (
            await self.session.execute(
                select(PatientFile).where(PatientFile.id == file_id).with_for_update()
            )
        ).scalar_one_or_none()
        if record is None:
            raise PatientFileError("That file was not found.", status_code=404)
        if record.withdrawn_at is not None:
            raise PatientFileError(
                f"Already withdrawn by {record.withdrawn_by_name}: {record.withdraw_reason}",
                status_code=409,
            )
        reason = (reason or "").strip()
        if len(reason) < 5:
            raise PatientFileError("Say why the file is being withdrawn. The reason is kept with the record.")
        record.withdrawn_at = _now()
        record.withdrawn_by_name = user.full_name
        record.withdraw_reason = reason[:1000]
        await self.session.commit()
        await self.session.refresh(record)
        return record
