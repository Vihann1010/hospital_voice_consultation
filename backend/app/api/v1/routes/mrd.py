"""The medical records bundle for an admission: checklist, build with progress, download."""
import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.permissions import Permission
from app.models.enums import AuditAction
from app.mrd import bundle

router = APIRouter(prefix="/mrd", tags=["medical-records"])

READ = require_permission(Permission.PATIENT_READ)


class BundleIn(BaseModel):
    items: List[str] = Field(min_length=1, max_length=500)
    date_from: Optional[date] = None
    date_to: Optional[date] = None


@router.get("/admissions/{admission_id}/checklist", dependencies=[Depends(READ)])
async def admission_checklist(admission_id: uuid.UUID, session: DbSession) -> dict:
    try:
        return await bundle.checklist(session, admission_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/admissions/{admission_id}/bundle", status_code=202, dependencies=[Depends(READ)])
async def build_bundle(admission_id: uuid.UUID, payload: BundleIn, session: DbSession, user: CurrentUser) -> dict:
    if payload.date_from and payload.date_to and payload.date_to < payload.date_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The start date is after the end date.")
    try:
        job = await bundle.start(session, admission_id, keys=payload.items, date_from=payload.date_from,
                                 date_to=payload.date_to, requested_by=user.full_name)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return job.public()


def _job(job_id: str) -> bundle.Job:
    job = bundle.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "That records file is no longer available. Build it again.")
    return job


@router.get("/jobs/{job_id}", dependencies=[Depends(READ)])
async def bundle_progress(job_id: str) -> dict:
    return _job(job_id).public()


@router.get("/jobs/{job_id}/file", dependencies=[Depends(READ)])
async def bundle_file(job_id: str, session: DbSession, user: CurrentUser, request: Request) -> Response:
    job = _job(job_id)
    if job.pdf is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The records file is still being put together.")
    from app.models.ipd import Admission

    admission = await session.get(Admission, job.admission_id)
    await audit_record(
        AuditAction.EXPORT_DOCUMENT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="admission_records", entity_id=job.admission_id,
        patient_id=admission.patient_id if admission else None, ip_address=client_ip(request),
        detail={"documents": job.total - len(job.skipped), "skipped": len(job.skipped), "pages": job.pages},
    )
    return Response(content=job.pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{job.filename}"'})
