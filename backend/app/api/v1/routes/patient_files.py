"""Patient file attachments: upload, list, open, withdraw.

Anyone who can read a patient's record can open their files. Attaching one is
the work of the front desk, doctors and nurses; withdrawing one keeps the file
and records who withdrew it and why.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.config import settings
from app.core.permissions import Permission
from app.models.enums import AuditAction, PatientFileCategory
from app.services.patient_file_service import CATEGORY_LABEL, PatientFileError, PatientFileService

router = APIRouter(prefix="/patient-files", tags=["patient-files"])

READ = require_permission(Permission.PATIENT_READ)
ATTACH = require_permission(Permission.REPORT_UPLOAD)


class PatientFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    consultation_id: Optional[uuid.UUID] = None
    admission_id: Optional[uuid.UUID] = None
    pad_document_id: Optional[uuid.UUID] = None
    category: PatientFileCategory
    title: str
    document_date: Optional[date] = None
    notes: Optional[str] = None
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_by_name: str
    withdrawn_at: Optional[datetime] = None
    withdrawn_by_name: Optional[str] = None
    withdraw_reason: Optional[str] = None
    created_at: datetime


class WithdrawIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


def _fail(exc: PatientFileError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.get("/categories", dependencies=[Depends(READ)])
async def categories() -> dict:
    return {"items": [{"key": key.value, "label": label} for key, label in CATEGORY_LABEL.items()]}


@router.post("", response_model=PatientFileOut, status_code=201, dependencies=[Depends(ATTACH)])
async def upload_file(
    session: DbSession,
    user: CurrentUser,
    request: Request,
    file: UploadFile = File(...),
    patient_id: uuid.UUID = Form(...),
    category: PatientFileCategory = Form(...),
    title: Optional[str] = Form(default=None, max_length=255),
    consultation_id: Optional[uuid.UUID] = Form(default=None),
    admission_id: Optional[uuid.UUID] = Form(default=None),
    pad_document_id: Optional[uuid.UUID] = Form(default=None),
    document_date: Optional[date] = Form(default=None),
    notes: Optional[str] = Form(default=None, max_length=2000),
) -> PatientFileOut:
    limit = settings.MAX_REPORT_UPLOAD_MB * 1024 * 1024
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"File is larger than the {settings.MAX_REPORT_UPLOAD_MB} MB limit.")
        chunks.append(chunk)
    try:
        record = await PatientFileService(session).upload(
            patient_id=patient_id, category=category, title=title,
            filename=file.filename or "file", content_type=file.content_type or "application/octet-stream",
            data=b"".join(chunks), user=user, consultation_id=consultation_id,
            admission_id=admission_id, pad_document_id=pad_document_id,
            document_date=document_date, notes=notes,
        )
    except PatientFileError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.FILE_UPLOAD,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="patient_file", entity_id=record.id, patient_id=record.patient_id,
        ip_address=client_ip(request),
        detail={"category": record.category.value, "title": record.title,
                "size_bytes": record.size_bytes, "pad_document_id":
                str(record.pad_document_id) if record.pad_document_id else None},
    )
    return PatientFileOut.model_validate(record)


@router.get("", response_model=List[PatientFileOut], dependencies=[Depends(READ)])
async def list_files(
    session: DbSession,
    patient_id: uuid.UUID = Query(...),
    admission_id: Optional[uuid.UUID] = Query(default=None),
    consultation_id: Optional[uuid.UUID] = Query(default=None),
    pad_document_id: Optional[uuid.UUID] = Query(default=None),
    category: Optional[PatientFileCategory] = Query(default=None),
    include_withdrawn: bool = Query(default=False),
) -> List[PatientFileOut]:
    records = await PatientFileService(session).list(
        patient_id=patient_id, admission_id=admission_id, consultation_id=consultation_id,
        pad_document_id=pad_document_id, category=category, include_withdrawn=include_withdrawn,
    )
    return [PatientFileOut.model_validate(item) for item in records]


@router.get("/{file_id}/file", dependencies=[Depends(READ)])
async def open_file(file_id: uuid.UUID, session: DbSession, user: CurrentUser, request: Request):
    service = PatientFileService(session)
    try:
        record = await service.get(file_id)
    except PatientFileError as exc:
        raise _fail(exc) from exc
    path = service.storage_path(record.stored_filename)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "The stored file is missing from the server.")
    await audit_record(
        AuditAction.EXPORT_DOCUMENT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="patient_file", entity_id=record.id, patient_id=record.patient_id,
        ip_address=client_ip(request), detail={"title": record.title, "withdrawn": bool(record.withdrawn_at)},
    )
    return FileResponse(path, media_type=record.content_type, filename=record.original_filename,
                        content_disposition_type="inline")


@router.post("/{file_id}/withdraw", response_model=PatientFileOut, dependencies=[Depends(ATTACH)])
async def withdraw_file(
    file_id: uuid.UUID, payload: WithdrawIn, session: DbSession, user: CurrentUser, request: Request
) -> PatientFileOut:
    try:
        record = await PatientFileService(session).withdraw(file_id, reason=payload.reason, user=user)
    except PatientFileError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.FILE_WITHDRAW,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="patient_file", entity_id=record.id, patient_id=record.patient_id,
        ip_address=client_ip(request), detail={"title": record.title, "reason": record.withdraw_reason},
    )
    return PatientFileOut.model_validate(record)
