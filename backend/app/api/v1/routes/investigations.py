import asyncio
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, get_investigation_service, require_permission
from app.core.permissions import Permission
from app.core.config import settings
from app.investigations import catalog
from app.investigations.extraction import extraction_capabilities
from app.models.enums import (
    Department,
    DocumentKind,
    InvestigationCategory,
    InvestigationPriority,
    UserRole,
)
from app.schemas.investigation_schemas import (
    CatalogOut,
    CategoryOut,
    FavoriteRequest,
    InvestigationOut,
    OrderCreateRequest,
    OrderListOut,
    OrderOut,
    PanelOut,
    ReportListItemOut,
    ReportListOut,
    ReportOut,
    ReportVersionHistoryOut,
    TemplateCreateRequest,
    TemplateOut,
    WorkspaceOut,
)
from app.services.investigation_service import InvestigationError, InvestigationService

router = APIRouter(prefix="/investigations", tags=["investigations"])

Service = Annotated[InvestigationService, Depends(get_investigation_service)]
READ_REPORTS = require_permission(Permission.REPORT_READ)
CLINICIAN = require_permission(Permission.ORDER_CREATE)


def _to_investigation_out(item) -> InvestigationOut:
    return InvestigationOut(
        code=item.code,
        name=item.name,
        category=item.category,
        category_label=catalog.CATEGORY_LABELS[item.category.value],
        aliases=item.aliases,
        specimen_or_site=item.specimen_or_site,
        preparation=item.preparation,
        turnaround=item.turnaround,
        departments=item.departments,
        note=item.note,
    )


def _template_out(template) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        department=template.department,
        codes=template.codes or [],
        shared=template.user_id is None,
    )


# ------------------------------------------------------------------ catalog
@router.get("/catalog", response_model=CatalogOut, dependencies=[Depends(READ_REPORTS)])
async def get_catalog(
    q: Optional[str] = Query(default=None, max_length=120),
    category: Optional[InvestigationCategory] = Query(default=None),
    department: Optional[Department] = Query(default=None),
) -> CatalogOut:
    """Searchable, categorised catalog. Panels are returned alongside."""
    matches = catalog.search(q, category=category, department=department)

    visible = catalog.search(None, department=department)
    counts: dict = {}
    for item in visible:
        counts[item.category.value] = counts.get(item.category.value, 0) + 1
    categories = [
        CategoryOut(value=value, label=label, count=counts.get(value, 0))
        for value, label in catalog.CATEGORY_LABELS.items()
    ]

    panels = [
        PanelOut(
            code=panel.code,
            name=panel.name,
            description=panel.description,
            members=[
                _to_investigation_out(member)
                for member in catalog.expand_codes([panel.code])
            ],
        )
        for panel in catalog.PANELS
        if not panel.departments or department is None or department in panel.departments
    ]

    return CatalogOut(
        categories=categories,
        investigations=[_to_investigation_out(item) for item in matches],
        panels=panels,
        total=len(matches),
    )


@router.get("/workspace", response_model=WorkspaceOut, dependencies=[Depends(READ_REPORTS)])
async def get_workspace(service: Service, user: CurrentUser) -> WorkspaceOut:
    """Favourites, recently used and templates for the signed-in clinician."""
    data = await service.workspace(user_id=user.id, department=user.department)
    return WorkspaceOut(
        favorites=data["favorites"],
        recent=data["recent"],
        templates=[_template_out(t) for t in data["templates"]],
        capabilities=extraction_capabilities(),
    )


@router.post("/favorites", response_model=List[str], dependencies=[Depends(READ_REPORTS)])
async def toggle_favorite(
    payload: FavoriteRequest, service: Service, user: CurrentUser
) -> List[str]:
    try:
        return await service.set_favorite(
            user_id=user.id, code=payload.code, favorite=payload.favorite
        )
    except InvestigationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/templates", response_model=TemplateOut, dependencies=[Depends(CLINICIAN)])
async def create_template(
    payload: TemplateCreateRequest, service: Service, user: CurrentUser
) -> TemplateOut:
    try:
        template = await service.create_template(
            user_id=user.id,
            name=payload.name,
            codes=payload.codes,
            description=payload.description,
            department=user.department,
            shared=payload.shared,
        )
    except InvestigationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _template_out(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(CLINICIAN)])
async def delete_template(template_id: uuid.UUID, service: Service, user: CurrentUser) -> None:
    try:
        removed = await service.delete_template(template_id, user_id=user.id)
    except InvestigationError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")


# ------------------------------------------------------------------- orders
@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(CLINICIAN)])
async def create_order(
    payload: OrderCreateRequest, service: Service, user: CurrentUser
) -> OrderOut:
    """Generate an investigation request. Only a clinician may order."""
    department = user.department or Department.ORTHOPEDICS
    try:
        order = await service.create_order(
            patient_id=payload.patient_id,
            consultation_id=payload.consultation_id,
            department=department,
            codes=payload.codes,
            priority=payload.priority,
            clinical_notes=payload.clinical_notes,
            provisional_diagnosis=payload.provisional_diagnosis,
            doctor_id=user.id,
            doctor_name=user.full_name,
            item_instructions=payload.item_instructions,
        )
    except InvestigationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return OrderOut.model_validate(order)


@router.get("/orders", response_model=OrderListOut, dependencies=[Depends(READ_REPORTS)])
async def list_orders(
    service: Service,
    patient_id: Optional[uuid.UUID] = Query(default=None),
    consultation_id: Optional[uuid.UUID] = Query(default=None),
) -> OrderListOut:
    if patient_id is None and consultation_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Provide patient_id or consultation_id"
        )
    orders = await service.list_orders(
        patient_id=patient_id, consultation_id=consultation_id
    )
    return OrderListOut(
        items=[OrderOut.model_validate(order) for order in orders], total=len(orders)
    )


@router.get("/orders/{order_id}", response_model=OrderOut, dependencies=[Depends(READ_REPORTS)])
async def get_order(order_id: uuid.UUID, service: Service) -> OrderOut:
    order = await service.get_order(order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut,
             dependencies=[Depends(CLINICIAN)])
async def cancel_order(order_id: uuid.UUID, service: Service) -> OrderOut:
    order = await service.cancel_order(order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return OrderOut.model_validate(order)


# ------------------------------------------------------------------ reports
def _report_list_item(report) -> ReportListItemOut:
    analysis = report.analysis or {}
    summary = analysis.get("summary") or {}
    return ReportListItemOut(
        id=report.id,
        group_id=report.group_id,
        version=report.version,
        title=report.title,
        original_filename=report.original_filename,
        content_type=report.content_type,
        document_kind=report.document_kind,
        status=report.status,
        abnormal_count=int(analysis.get("abnormal_count") or 0),
        critical_count=int(analysis.get("critical_count") or 0),
        clarity=analysis.get("clarity"),
        needs_manual_check=bool(
            analysis.get("needs_manual_check")
            or (analysis.get("prescription") or {}).get("needs_manual_check")
        ),
        headline=summary.get("headline"),
        uploaded_by_name=report.uploaded_by_name,
        created_at=report.created_at,
    )


@router.post("/reports", response_model=ReportOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(READ_REPORTS)])
async def upload_report(
    service: Service,
    user: CurrentUser,
    file: UploadFile = File(..., description="PDF, image or scanned report"),
    patient_id: uuid.UUID = Form(...),
    consultation_id: Optional[uuid.UUID] = Form(default=None),
    order_id: Optional[uuid.UUID] = Form(default=None),
    replaces_id: Optional[uuid.UUID] = Form(default=None),
    revision_note: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
    document_kind: Optional[DocumentKind] = Form(
        default=None,
        description="What this document is. Checked against the text itself; "
                    "when the two disagree nothing is interpreted.",
    ),
) -> ReportOut:
    """Upload a report. Text is extracted, values are compared against reference
    ranges arithmetically, and a narrative summary is generated."""
    # Read in chunks and abort as soon as the limit is passed, so an oversized
    # upload is never fully buffered into memory before being rejected.
    limit = settings.MAX_REPORT_UPLOAD_MB * 1024 * 1024
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > limit:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"File is larger than the {settings.MAX_REPORT_UPLOAD_MB} MB limit.",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    try:
        report = await service.upload_report(
            patient_id=patient_id,
            consultation_id=consultation_id,
            order_id=order_id,
            replaces_id=replaces_id,
            revision_note=revision_note,
            title=title or (file.filename or "Report"),
            filename=file.filename or "report",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            uploaded_by_id=user.id,
            uploaded_by_name=user.full_name,
            department=user.department or Department.ORTHOPEDICS,
            document_kind=document_kind,
        )
    except InvestigationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ReportOut.model_validate(report)


@router.get("/reports", response_model=ReportListOut, dependencies=[Depends(READ_REPORTS)])
async def list_reports(
    service: Service,
    patient_id: Optional[uuid.UUID] = Query(default=None),
    consultation_id: Optional[uuid.UUID] = Query(default=None),
    include_superseded: bool = Query(default=False),
) -> ReportListOut:
    if patient_id is None and consultation_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Provide patient_id or consultation_id"
        )
    reports = await service.list_reports(
        patient_id=patient_id,
        consultation_id=consultation_id,
        include_superseded=include_superseded,
    )
    return ReportListOut(
        items=[_report_list_item(report) for report in reports], total=len(reports)
    )


@router.get("/reports/{report_id}", response_model=ReportOut, dependencies=[Depends(READ_REPORTS)])
async def get_report(report_id: uuid.UUID, service: Service) -> ReportOut:
    report = await service.get_report(report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return ReportOut.model_validate(report)


@router.get("/reports/{report_id}/versions", response_model=ReportVersionHistoryOut,
            dependencies=[Depends(READ_REPORTS)])
async def report_versions(report_id: uuid.UUID, service: Service) -> ReportVersionHistoryOut:
    """Every version ever uploaded for this report, newest first."""
    report, versions = await service.version_history(report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return ReportVersionHistoryOut(
        group_id=report.group_id,
        current=ReportOut.model_validate(report),
        versions=[_report_list_item(version) for version in versions],
    )


@router.get("/reports/{report_id}/file", dependencies=[Depends(READ_REPORTS)])
async def download_report(report_id: uuid.UUID, service: Service) -> FileResponse:
    report = await service.get_report(report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    path = service.storage_path(report.stored_filename)
    if not await asyncio.to_thread(path.exists):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The stored file is missing")
    return FileResponse(
        path,
        media_type=report.content_type,
        filename=report.original_filename,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"},
    )


@router.post("/reports/{report_id}/reprocess", response_model=ReportOut,
             dependencies=[Depends(CLINICIAN)])
async def reprocess_report(
    report_id: uuid.UUID, service: Service, user: CurrentUser
) -> ReportOut:
    """Re-run extraction and analysis, e.g. after OCR is installed."""
    report = await service.process_report(
        report_id, department=user.department or Department.ORTHOPEDICS
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return ReportOut.model_validate(report)
