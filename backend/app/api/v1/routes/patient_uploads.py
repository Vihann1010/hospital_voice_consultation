"""Patient-facing upload of previous reports.

After the voice intake ends, the patient is invited to photograph or upload
any earlier reports they have brought with them. Those go straight onto the
doctor's record for this visit, so an old X-ray or blood test is on screen
before the consultation starts rather than being handed over on paper halfway
through it.

Authentication is the consultation session token the patient already holds —
the same short-lived, single-consultation token that authorised the voice
call. There is no patient login, and this endpoint deliberately does not
create one: the token grants exactly one capability, attaching a file to one
consultation, and expires with the visit.
"""
import uuid
from typing import Annotated, List, Optional

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_investigation_service
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import TOKEN_TYPE_CONSULTATION, TOKEN_TYPE_UPLOAD
from app.models.enums import DocumentKind
from app.services.investigation_service import InvestigationError, InvestigationService

logger = get_logger(__name__)
router = APIRouter(prefix="/patient-uploads", tags=["patient"])

Service = Annotated[InvestigationService, Depends(get_investigation_service)]

MAX_FILES_PER_CONSULTATION = 10


class UploadedReportOut(BaseModel):
    id: uuid.UUID
    title: str
    original_filename: str
    size_bytes: int
    status: str
    document_kind: Optional[DocumentKind] = None


def _consultation_from_token(session_token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            session_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "This upload link has expired."
        ) from exc
    # Two tokens reach here. The consultation token belongs to the patient's
    # own voice session and lasts as long as it does; the upload token is the
    # short-lived one behind the QR code the nurse shows. Both grant exactly
    # this one capability and nothing else.
    if payload.get("type") not in (TOKEN_TYPE_CONSULTATION, TOKEN_TYPE_UPLOAD):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid upload link.")
    consultation_id = payload.get("consultation_id")
    if not consultation_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid upload link.")
    return uuid.UUID(str(consultation_id))


@router.post("/reports", response_model=UploadedReportOut,
             status_code=status.HTTP_201_CREATED)
async def upload_previous_report(
    service: Service,
    session_token: str = Form(...),
    file: UploadFile = File(...),
    title: str = Form(default=""),
    document_kind: Optional[DocumentKind] = Form(default=None),
) -> UploadedReportOut:
    """Attach one previous report to this consultation.

    Runs the same validation and extraction as a staff upload: content is
    checked by magic bytes rather than by the filename, and the file is put
    through text extraction and reference-range analysis so the doctor sees
    values, not just an attachment.
    """
    consultation_id = _consultation_from_token(session_token)

    consultation = await service.consultations.get(consultation_id)
    if consultation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found.")

    existing = await service.reports.list_for_consultation(consultation_id)
    if len(existing) >= MAX_FILES_PER_CONSULTATION:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"You can upload up to {MAX_FILES_PER_CONSULTATION} reports for this visit. "
            "Please hand any others to the front desk.",
        )

    limit = settings.MAX_REPORT_UPLOAD_MB * 1024 * 1024
    chunks: List[bytes] = []
    received = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > limit:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"That file is larger than {settings.MAX_REPORT_UPLOAD_MB} MB. "
                "Try photographing the report instead of scanning it.",
            )
        chunks.append(chunk)

    try:
        report = await service.upload_report(
            patient_id=consultation.patient_id,
            consultation_id=consultation_id,
            order_id=None,
            replaces_id=None,
            revision_note=None,
            title=(title or "").strip() or "Previous report (patient upload)",
            filename=file.filename or "report",
            content_type=file.content_type or "application/octet-stream",
            data=b"".join(chunks),
            uploaded_by_id=None,
            uploaded_by_name="Patient",
            department=consultation.department,
            document_kind=document_kind,
        )
    except InvestigationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    logger.info(
        "patient_report_uploaded",
        extra={"consultation_id": str(consultation_id), "report_id": str(report.id),
               "bytes": received},
    )
    return UploadedReportOut(
        id=report.id,
        title=report.title,
        original_filename=report.original_filename,
        size_bytes=report.size_bytes,
        status=report.status.value,
        document_kind=report.document_kind,
    )
