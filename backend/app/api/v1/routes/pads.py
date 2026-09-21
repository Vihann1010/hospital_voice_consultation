"""Visit Pad endpoints: layouts, documents, the three habits, and printing.

Reading needs only consultation access. Writing a pad and signing one are
separate permissions, and changing what a whole department's pad looks like
is administration — see `app/core/permissions.py`.
"""
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.deps import CurrentUser, get_pad_service, require_module, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.permissions import Permission, has_permission
from app.models.enums import AuditAction, Department, PadStatus
from app.models.patient import Patient
from app.modules import Module
from app.pads.defaults import DOCUMENT_TYPES, PROTECTED_SECTIONS, document_type as type_spec
from app.pads import forms
from app.pads.forms_pdf import render_form_pdf
from app.pads.pdf import render_pad_pdf
from app.pads.sections import TEMPLATE_VARIABLES
from app.printing.layout import load_layout
from app.schemas.pad_schemas import (
    CatalogueSuggestionOut,
    PadAmendIn,
    PadApplyTemplateIn,
    PadArrangeIn,
    PadDocumentOut,
    PadDocumentSummaryOut,
    PadLayoutIn,
    PadLayoutOut,
    PadSaveIn,
    PadTemplateIn,
    PadTemplateOut,
)
from app.services.pad_service import PadError, PadService

router = APIRouter(prefix="/pads", tags=["visit-pad"])

Service = Annotated[PadService, Depends(get_pad_service)]

READ = require_permission(Permission.CONSULTATION_READ)
WRITE = require_permission(Permission.CLINICAL_DOCUMENT_WRITE)
SIGN = require_permission(Permission.CLINICAL_DOCUMENT_SIGN)


def _fail(exc: PadError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _require_authority(user, document_type: str, *, sign: bool) -> None:
    """May this person write, or sign, this kind of document?

    Decided by whose document it is. A progress note is the doctor's to write
    and sign; a nursing note is the nurse's. A doctor holding every clinical
    permission still does not sign a nurse's shift note, and a nurse does not
    write a progress note.
    """
    spec = type_spec(document_type)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There is no document type called {document_type!r}.")
    if spec.authority == "nursing":
        needed = Permission.NURSING_DOCUMENT
        who = "nursing staff"
    else:
        needed = Permission.CLINICAL_DOCUMENT_SIGN if sign else Permission.CLINICAL_DOCUMENT_WRITE
        who = "a doctor"
    if not has_permission(user.role, needed):
        verb = "signed" if sign else "written"
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"{spec.label} is {verb} by {who}."
        )


async def _authorise(service: PadService, user, document_id: uuid.UUID, *, sign: bool) -> None:
    try:
        document = await service.get(document_id)
    except PadError as exc:
        raise _fail(exc) from exc
    _require_authority(user, document.document_type, sign=sign)


def _template_out(template, user_id: uuid.UUID) -> PadTemplateOut:
    return PadTemplateOut(
        id=template.id,
        document_type=template.document_type,
        name=template.name,
        description=template.description,
        owner_name=template.owner_name,
        shared=template.owner_id is None,
        use_count=template.use_count,
        section_keys=sorted((template.values or {}).keys()),
    )


# ------------------------------------------------------------------ layouts
@router.get("/document-types", dependencies=[Depends(READ)])
async def document_types() -> dict:
    return {
        "items": [
            {"key": key, "label": label, "scope": type_spec(key).scope,
             "authority": type_spec(key).authority, "family": type_spec(key).family,
             "requires": type_spec(key).requires}
            for key, label in DOCUMENT_TYPES.items()
        ]
    }


@router.get("/forms/{document_type}", dependencies=[Depends(READ)])
async def form_wording(document_type: str) -> dict:
    """The fixed wording a consent form prints, so the doctor sees what the patient will sign."""
    spec = type_spec(document_type)
    if spec is None or not spec.family:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a certificate or consent form.")
    return {
        "key": spec.key,
        "label": spec.label,
        "label_hi": forms.TITLE_HI.get(spec.key),
        "family": spec.family,
        "requires": spec.requires,
        "statement": forms.STATEMENTS.get(spec.key),
    }


@router.get("/layouts/{document_type}", response_model=PadLayoutOut, dependencies=[Depends(READ)])
async def get_layout(
    document_type: str,
    service: Service,
    user: CurrentUser,
    department: Optional[Department] = Query(default=None),
) -> PadLayoutOut:
    try:
        row, sections, scope = await service.resolve_layout(
            document_type, department=department or user.department, user_id=user.id
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return PadLayoutOut(
        document_type=document_type,
        document_label=DOCUMENT_TYPES[document_type],
        scope=scope,
        name=row.name if row else DOCUMENT_TYPES[document_type],
        sections=sections,
        revision=row.revision if row else 0,
        updated_by_name=row.updated_by_name if row else None,
        variables=TEMPLATE_VARIABLES,
        protected=PROTECTED_SECTIONS.get(document_type, {}),
        locked=bool(type_spec(document_type).family),
    )


@router.put("/layouts/{document_type}", response_model=PadLayoutOut, dependencies=[Depends(WRITE)])
async def save_layout(
    document_type: str,
    payload: PadLayoutIn,
    service: Service,
    user: CurrentUser,
    request: Request,
) -> PadLayoutOut:
    # A personal layout is the doctor's own business. Anything wider changes
    # what prints on every colleague's documents.
    if payload.scope != "personal" and not has_permission(user.role, Permission.PAD_LAYOUT_MANAGE):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Changing a department's or the hospital's pad needs an administrator. "
            "You can save this as your own layout instead.",
        )
    department = payload.department or user.department
    try:
        row = await service.save_layout(
            document_type,
            scope=payload.scope,
            name=payload.name,
            sections=payload.sections,
            department=department,
            user=user,
        )
    except PadError as exc:
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.PAD_LAYOUT_CHANGE,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="pad_layout", entity_id=row.id, ip_address=client_ip(request),
        detail={"document_type": document_type, "scope": payload.scope,
                "revision": row.revision, "sections": len(row.sections)},
    )
    return PadLayoutOut(
        document_type=document_type,
        document_label=DOCUMENT_TYPES[document_type],
        scope=payload.scope,
        name=row.name,
        sections=row.sections,
        revision=row.revision,
        updated_by_name=row.updated_by_name,
        variables=TEMPLATE_VARIABLES,
    )


@router.delete("/layouts/{document_type}", status_code=204, dependencies=[Depends(WRITE)])
async def reset_layout(
    document_type: str,
    service: Service,
    user: CurrentUser,
    request: Request,
    scope: str = Query(...),
    department: Optional[Department] = Query(default=None),
) -> Response:
    if scope != "personal" and not has_permission(user.role, Permission.PAD_LAYOUT_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can reset that layout.")
    try:
        removed = await service.reset_layout(
            document_type, scope=scope, department=department or user.department, user=user
        )
    except PadError as exc:
        raise _fail(exc) from exc
    if removed:
        await audit_record(
            AuditAction.PAD_LAYOUT_CHANGE,
            actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
            entity_type="pad_layout", ip_address=client_ip(request),
            detail={"document_type": document_type, "scope": scope, "reset": True},
        )
    return Response(status_code=204)


# ---------------------------------------------------------------- documents
@router.post(
    "/consultations/{consultation_id}/{document_type}",
    response_model=PadDocumentOut,
    dependencies=[Depends(WRITE)],
)
async def open_document(
    consultation_id: uuid.UUID, document_type: str, service: Service, user: CurrentUser
) -> PadDocumentOut:
    """The pad for this consultation: the draft, the signed copy, or a new draft."""
    try:
        document = await service.open_for_consultation(consultation_id, document_type, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.post(
    "/admissions/{admission_id}/{document_type}",
    response_model=PadDocumentOut,
    dependencies=[Depends(READ)],
)
async def open_admission_document(
    admission_id: uuid.UUID,
    document_type: str,
    service: Service,
    user: CurrentUser,
    new: bool = Query(default=False, description="Start a fresh note even if one is unfinished"),
) -> PadDocumentOut:
    """An inpatient document: the one for this admission, or a new note."""
    _require_authority(user, document_type, sign=False)
    try:
        document = await service.open_for_admission(
            admission_id, document_type, user=user, new=new
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.post(
    "/surgeries/{surgery_id}/{document_type}",
    response_model=PadDocumentOut,
    dependencies=[Depends(READ)],
)
async def open_surgery_document(
    surgery_id: uuid.UUID, document_type: str, service: Service, user: CurrentUser
) -> PadDocumentOut:
    """A theatre note for one case."""
    _require_authority(user, document_type, sign=False)
    try:
        document = await service.open_for_surgery(surgery_id, document_type, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.post(
    "/patients/{patient_id}/{document_type}",
    response_model=PadDocumentOut,
    dependencies=[Depends(READ)],
)
async def open_patient_document(
    patient_id: uuid.UUID,
    document_type: str,
    service: Service,
    user: CurrentUser,
    consultation_id: Optional[uuid.UUID] = Query(default=None),
    admission_id: Optional[uuid.UUID] = Query(default=None),
    surgery_id: Optional[uuid.UUID] = Query(default=None),
    order_item_id: Optional[uuid.UUID] = Query(default=None),
    new: bool = Query(default=False, description="Start a fresh form even if one is unfinished"),
) -> PadDocumentOut:
    """A certificate, consent form or radiology report, optionally linked to what it is about."""
    _require_authority(user, document_type, sign=False)
    try:
        document = await service.open_for_patient(
            patient_id, document_type, user=user, consultation_id=consultation_id,
            admission_id=admission_id, surgery_id=surgery_id, order_item_id=order_item_id, new=new,
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.get("/radiology/worklist",
            dependencies=[Depends(READ), Depends(require_module(Module.RADIOLOGY))])
async def radiology_worklist(
    service: Service,
    include_reported: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    """Imaging studies ordered and waiting for a report."""
    return {"items": await service.radiology_worklist(include_reported=include_reported, limit=limit)}


@router.post("/documents/{document_id}/paper-signed", response_model=PadDocumentOut,
             dependencies=[Depends(READ)])
async def record_paper_signed(
    document_id: uuid.UUID, service: Service, user: CurrentUser, request: Request
) -> PadDocumentOut:
    """The patient's signed paper copy of a consent form has been received."""
    if not (has_permission(user.role, Permission.CLINICAL_DOCUMENT_WRITE)
            or has_permission(user.role, Permission.NURSING_DOCUMENT)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Recording a signed consent is for doctors and nurses.")
    try:
        document = await service.record_paper_signed(document_id, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.CONSENT_PAPER_SIGNED,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="pad_document", entity_id=document.id, patient_id=document.patient_id,
        ip_address=client_ip(request),
        detail={"document_type": document.document_type, "serial_number": document.serial_number,
                "version": document.version},
    )
    return PadDocumentOut.model_validate(document)


@router.get("/documents", response_model=List[PadDocumentSummaryOut], dependencies=[Depends(READ)])
async def list_documents(
    service: Service,
    patient_id: Optional[uuid.UUID] = Query(default=None),
    consultation_id: Optional[uuid.UUID] = Query(default=None),
    admission_id: Optional[uuid.UUID] = Query(default=None),
    surgery_id: Optional[uuid.UUID] = Query(default=None),
    document_type: Optional[str] = Query(default=None),
    include_superseded: bool = Query(default=False),
) -> List[PadDocumentSummaryOut]:
    try:
        documents = await service.list_documents(
            patient_id=patient_id,
            consultation_id=consultation_id,
            admission_id=admission_id,
            surgery_id=surgery_id,
            document_type=document_type,
            include_superseded=include_superseded,
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return [PadDocumentSummaryOut.model_validate(document) for document in documents]


@router.get("/documents/{document_id}", response_model=PadDocumentOut, dependencies=[Depends(READ)])
async def get_document(document_id: uuid.UUID, service: Service) -> PadDocumentOut:
    try:
        return PadDocumentOut.model_validate(await service.get(document_id))
    except PadError as exc:
        raise _fail(exc) from exc


@router.patch("/documents/{document_id}", response_model=PadDocumentOut, dependencies=[Depends(READ)])
async def save_document(
    document_id: uuid.UUID, payload: PadSaveIn, service: Service, user: CurrentUser
) -> PadDocumentOut:
    await _authorise(service, user, document_id, sign=False)
    try:
        document = await service.save_values(
            document_id, values=payload.values, base_updated_at=payload.base_updated_at, user=user
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.put(
    "/documents/{document_id}/arrangement",
    response_model=PadDocumentOut,
    dependencies=[Depends(READ)],
)
async def arrange_document(
    document_id: uuid.UUID, payload: PadArrangeIn, service: Service, user: CurrentUser
) -> PadDocumentOut:
    await _authorise(service, user, document_id, sign=False)
    try:
        document = await service.arrange(
            document_id, arrangement=[item.model_dump() for item in payload.sections], user=user
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.delete("/documents/{document_id}", status_code=204, dependencies=[Depends(READ)])
async def discard_document(document_id: uuid.UUID, service: Service, user: CurrentUser) -> Response:
    await _authorise(service, user, document_id, sign=False)
    try:
        await service.discard(document_id, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    return Response(status_code=204)


@router.post("/documents/{document_id}/sign", response_model=PadDocumentOut, dependencies=[Depends(READ)])
async def sign_document(
    document_id: uuid.UUID, service: Service, user: CurrentUser, request: Request
) -> PadDocumentOut:
    await _authorise(service, user, document_id, sign=True)
    try:
        document = await service.sign(document_id, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.PAD_SIGN,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="pad_document", entity_id=document.id, patient_id=document.patient_id,
        ip_address=client_ip(request),
        detail={"document_type": document.document_type, "version": document.version,
                "supersedes": str(document.supersedes_id) if document.supersedes_id else None},
    )
    return PadDocumentOut.model_validate(document)


@router.post("/documents/{document_id}/amend", response_model=PadDocumentOut, dependencies=[Depends(READ)])
async def amend_document(
    document_id: uuid.UUID,
    payload: PadAmendIn,
    service: Service,
    user: CurrentUser,
    request: Request,
) -> PadDocumentOut:
    await _authorise(service, user, document_id, sign=True)
    try:
        document = await service.amend(document_id, reason=payload.reason, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    await audit_record(
        AuditAction.PAD_AMEND,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="pad_document", entity_id=document.supersedes_id or document.id,
        patient_id=document.patient_id, ip_address=client_ip(request),
        detail={"reason": payload.reason, "new_version": document.version,
                "draft_id": str(document.id)},
    )
    return PadDocumentOut.model_validate(document)


# ---------------------------------------------------------- the three habits
@router.get(
    "/documents/{document_id}/previous",
    response_model=Optional[PadDocumentOut],
    dependencies=[Depends(READ)],
)
async def previous_visit(document_id: uuid.UUID, service: Service) -> Optional[PadDocumentOut]:
    try:
        previous = await service.previous_visit(document_id)
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(previous) if previous else None


@router.post(
    "/documents/{document_id}/copy-previous",
    response_model=PadDocumentOut,
    dependencies=[Depends(READ)],
)
async def copy_previous(document_id: uuid.UUID, service: Service, user: CurrentUser) -> PadDocumentOut:
    await _authorise(service, user, document_id, sign=False)
    try:
        document = await service.copy_previous(document_id, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.post(
    "/documents/{document_id}/apply-template",
    response_model=PadDocumentOut,
    dependencies=[Depends(READ)],
)
async def apply_template(
    document_id: uuid.UUID, payload: PadApplyTemplateIn, service: Service, user: CurrentUser
) -> PadDocumentOut:
    await _authorise(service, user, document_id, sign=False)
    try:
        document = await service.apply_template(
            document_id, template_id=payload.template_id, replace=payload.replace, user=user
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return PadDocumentOut.model_validate(document)


@router.get("/templates", response_model=List[PadTemplateOut], dependencies=[Depends(READ)])
async def list_templates(
    service: Service,
    user: CurrentUser,
    document_type: str = Query(...),
    department: Optional[Department] = Query(default=None),
) -> List[PadTemplateOut]:
    try:
        templates = await service.list_templates(
            document_type, department=department or user.department, user=user
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return [_template_out(template, user.id) for template in templates]


@router.post("/templates", response_model=PadTemplateOut, status_code=201, dependencies=[Depends(READ)])
async def save_template(payload: PadTemplateIn, service: Service, user: CurrentUser) -> PadTemplateOut:
    await _authorise(service, user, payload.document_id, sign=False)
    if payload.shared and not has_permission(user.role, Permission.TEMPLATE_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sharing a template with the department needs template management.")
    try:
        template = await service.save_template(
            payload.document_id,
            name=payload.name,
            description=payload.description,
            shared=payload.shared,
            user=user,
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return _template_out(template, user.id)


@router.delete("/templates/{template_id}", status_code=204, dependencies=[Depends(READ)])
async def delete_template(template_id: uuid.UUID, service: Service, user: CurrentUser) -> Response:
    try:
        await service.delete_template(
            template_id,
            user=user,
            may_manage_shared=has_permission(user.role, Permission.TEMPLATE_MANAGE),
        )
    except PadError as exc:
        raise _fail(exc) from exc
    return Response(status_code=204)


@router.post("/documents/{document_id}/draft-discharge", dependencies=[Depends(READ)])
async def draft_discharge(document_id: uuid.UUID, service: Service, user: CurrentUser) -> dict:
    """Fill a discharge summary's empty sections from the ward record."""
    await _authorise(service, user, document_id, sign=False)
    try:
        document, filled, uncertain = await service.draft_discharge_with_ai(document_id, user=user)
    except PadError as exc:
        raise _fail(exc) from exc
    return {
        "document": PadDocumentOut.model_validate(document).model_dump(mode="json"),
        "filled": filled,
        "uncertain": uncertain,
    }


# ---------------------------------------------------------------- catalogue
@router.get(
    "/catalogue/{category}",
    response_model=List[CatalogueSuggestionOut],
    dependencies=[Depends(READ)],
)
async def catalogue(
    category: str,
    service: Service,
    user: CurrentUser,
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=12, ge=1, le=40),
) -> List[CatalogueSuggestionOut]:
    entries = await service.suggest(category, query=q, department=user.department, limit=limit)
    return [CatalogueSuggestionOut(text=entry.text, use_count=entry.use_count) for entry in entries]


# ---------------------------------------------------------------- printing
@router.get("/documents/{document_id}/pdf", dependencies=[Depends(READ)])
async def document_pdf(
    document_id: uuid.UUID, service: Service, user: CurrentUser, request: Request
) -> Response:
    try:
        document = await service.get(document_id)
    except PadError as exc:
        raise _fail(exc) from exc
    patient = await service.session.get(Patient, document.patient_id)
    layout = await load_layout(service.session, document.document_type)

    count = await service.mark_printed(document)
    watermark = None
    if document.status == PadStatus.DRAFT:
        watermark = "DRAFT"
    elif document.status == PadStatus.SUPERSEDED:
        watermark = "SUPERSEDED"
    elif count > 1 and layout.watermark_duplicates:
        watermark = "DUPLICATE"

    spec = type_spec(document.document_type)
    if spec is not None and spec.family in ("certificate", "consent"):
        from sqlalchemy import select

        from app.models.consultant import Consultant
        from app.models.ipd import Admission

        doctor = None
        if document.signed_by_id:
            doctor = (
                await service.session.execute(
                    select(Consultant).where(Consultant.user_id == document.signed_by_id)
                )
            ).scalar_one_or_none()
        admission = (
            await service.session.get(Admission, document.admission_id) if document.admission_id else None
        )
        pdf = render_form_pdf(document=document, patient=patient, admission=admission, doctor=doctor,
                              layout=layout, watermark=watermark)
    else:
        pdf = render_pad_pdf(document=document, patient=patient, layout=layout, watermark=watermark)
    await audit_record(
        AuditAction.EXPORT_DOCUMENT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="pad_document", entity_id=document.id, patient_id=document.patient_id,
        ip_address=client_ip(request),
        detail={"document_type": document.document_type, "print_count": count,
                "watermark": watermark},
    )
    filename = f"{document.document_type}-{patient.uhid or document.id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
