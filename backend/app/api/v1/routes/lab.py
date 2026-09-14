"""Laboratory endpoints: the test list, requests, results, verification, printing.

Registering tests is counter and ward work; entering results is the bench's;
verifying them is a doctor's. The test list holds the reference ranges every
flag is computed from, so editing it is its own permission, and reviewing a
test's ranges is part of the authority to verify.
"""
import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.config import settings
from app.core.permissions import Permission
from app.lab import defaults, rules
from app.lab.report_pdf import render_lab_report
from app.models.emr import Invoice
from app.models.enums import AdmissionStatus, AuditAction
from app.models.ipd import Admission
from app.models.lab import LabMaster, LabRequest, LabTest
from app.models.patient import Patient
from app.printing.layout import load_layout
from app.services.lab_service import LabError, LabService, parameter_dict, patient_sex

router = APIRouter(prefix="/lab", tags=["laboratory"])

READ = require_permission(Permission.PATIENT_READ)
REGISTER = require_permission(Permission.LAB_REGISTER)
ENTER = require_permission(Permission.LAB_RESULT_ENTER)
VERIFY = require_permission(Permission.LAB_RESULT_VERIFY)
MASTERS = require_permission(Permission.LAB_MASTER_MANAGE)

PRINTOUT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}


# ------------------------------------------------------------------ schemas
class MasterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(max_length=16)
    name: str = Field(min_length=1, max_length=120)
    code: Optional[str] = Field(default=None, max_length=32)
    category: Optional[str] = Field(default=None, max_length=64)
    position: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True


class ParameterIn(BaseModel):
    id: Optional[uuid.UUID] = None
    name: str = Field(default="", max_length=120)
    analyte_key: Optional[str] = Field(default=None, max_length=64)
    aliases: List[str] = Field(default_factory=list, max_length=20)
    result_type: str = Field(default="numeric", max_length=16)
    unit: Optional[str] = Field(default=None, max_length=32)
    method: Optional[str] = Field(default=None, max_length=120)
    choices: List[str] = Field(default_factory=list, max_length=30)
    normal_values: List[str] = Field(default_factory=list, max_length=30)
    ranges: List[Dict[str, Any]] = Field(default_factory=list, max_length=12)
    range_text: Optional[str] = Field(default=None, max_length=255)
    print_default: bool = True
    is_active: bool = True


class TestIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    group_name: str = Field(default="General", max_length=64)
    specimen: Optional[str] = Field(default=None, max_length=120)
    service_code: Optional[str] = Field(default=None, max_length=32)
    catalog_code: Optional[str] = Field(default=None, max_length=64)
    is_culture: bool = False
    turnaround_hours: int = Field(default=24, ge=1, le=720)
    interpretation: Optional[str] = Field(default=None, max_length=4000)
    position: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True
    notes: Optional[str] = Field(default=None, max_length=2000)
    parameters: List[ParameterIn] = Field(default_factory=list, max_length=80)


class TestLineIn(BaseModel):
    test_id: uuid.UUID
    order_item_id: Optional[uuid.UUID] = None


class RegisterIn(BaseModel):
    patient_id: uuid.UUID
    tests: List[TestLineIn] = Field(min_length=1, max_length=40)
    billing: str = Field(default="invoice", max_length=16)
    admission_id: Optional[uuid.UUID] = None
    consultation_id: Optional[uuid.UUID] = None
    order_id: Optional[uuid.UUID] = None
    referred_by: Optional[str] = Field(default=None, max_length=255)
    consultant_id: Optional[uuid.UUID] = None
    priority: str = Field(default="routine", max_length=16)
    clinical_notes: Optional[str] = Field(default=None, max_length=2000)


class BillIn(BaseModel):
    billing: str = Field(max_length=16)
    admission_id: Optional[uuid.UUID] = None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class CancelIn(ReasonIn):
    item_ids: Optional[List[uuid.UUID]] = None


class ResultsIn(BaseModel):
    values: Dict[str, Optional[str]] = Field(default_factory=dict)
    prints: Dict[str, bool] = Field(default_factory=dict)
    remarks: Optional[str] = Field(default=None, max_length=2000)
    culture: Optional[Dict[str, Any]] = None


class VerifyIn(BaseModel):
    critical_note: Optional[str] = Field(default=None, max_length=1000)


# -------------------------------------------------------------- serialisers
def _fail(exc: LabError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _master(master: LabMaster) -> Dict[str, Any]:
    return {"id": master.id, "kind": master.kind, "name": master.name, "code": master.code,
            "category": master.category, "position": master.position, "is_active": master.is_active}


def _test(test: LabTest, *, include_inactive: bool = False) -> Dict[str, Any]:
    return {
        "id": test.id, "code": test.code, "name": test.name, "group_name": test.group_name,
        "specimen": test.specimen, "service_code": test.service_code, "catalog_code": test.catalog_code,
        "is_culture": test.is_culture, "turnaround_hours": test.turnaround_hours,
        "interpretation": test.interpretation, "position": test.position, "is_active": test.is_active,
        "notes": test.notes, "ranges_reviewed_at": test.ranges_reviewed_at,
        "ranges_reviewed_by_name": test.ranges_reviewed_by_name,
        "parameters": [parameter_dict(parameter) for parameter in sorted(test.parameters, key=lambda p: p.position)
                       if include_inactive or parameter.is_active],
    }


def _patient(patient: Patient) -> Dict[str, Any]:
    return {"id": patient.id, "name": patient.name, "uhid": patient.uhid, "age": patient.age,
            "gender": patient.gender.value, "phone_number": patient.phone_number}


def _item(item, *, parameters=None, ranges_reviewed=None) -> Dict[str, Any]:
    return {
        "id": item.id, "test_id": item.test_id, "order_item_id": item.order_item_id, "code": item.code,
        "name": item.name, "group_name": item.group_name, "specimen": item.specimen,
        "is_culture": item.is_culture, "unit_rate_paise": item.unit_rate_paise, "status": item.status,
        "results": item.results or [], "culture": item.culture, "remarks": item.remarks,
        "critical_note": item.critical_note, "entered_at": item.entered_at,
        "entered_by_name": item.entered_by_name, "verified_at": item.verified_at,
        "verified_by_name": item.verified_by_name, "verifier_qualification": item.verifier_qualification,
        "verifier_registration": item.verifier_registration, "version": item.version,
        "amendments": [{"version": entry.get("version"), "reason": entry.get("reason"),
                        "reopened_by_name": entry.get("reopened_by_name"),
                        "reopened_at": entry.get("reopened_at")} for entry in item.amendments or []],
        "cancelled_at": item.cancelled_at, "cancel_reason": item.cancel_reason,
        "parameters": parameters, "ranges_reviewed": ranges_reviewed,
    }


async def _request(session, service: LabService, request: LabRequest, *, entry: bool = False) -> Dict[str, Any]:
    patient = await session.get(Patient, request.patient_id)
    admission = await session.get(Admission, request.admission_id) if request.admission_id else None
    invoice = await session.get(Invoice, request.invoice_id) if request.invoice_id else None
    sex, age = patient_sex(patient), patient.age
    items = []
    for item in sorted(request.items, key=lambda entry_item: entry_item.position):
        parameters = None
        reviewed = None
        if entry and item.test_id:
            test = await session.get(LabTest, item.test_id)
            reviewed = bool(test and (test.is_culture or test.ranges_reviewed_at))
            if item.status not in ("verified", "cancelled") and not item.is_culture:
                parameters = await service.active_parameters(item.test_id)
                for parameter in parameters:
                    parameter["range_preview"] = parameter.get("range_text") or rules.range_text(
                        rules.select_range(parameter.get("ranges") or [], sex=sex, age=age))
        items.append(_item(item, parameters=parameters, ranges_reviewed=reviewed))
    return {
        "id": request.id, "lab_number": request.lab_number, "status": request.status,
        "billing": request.billing, "priority": request.priority, "referred_by": request.referred_by,
        "consultant_id": request.consultant_id, "clinical_notes": request.clinical_notes,
        "consultation_id": request.consultation_id, "order_id": request.order_id,
        "registered_by_name": request.registered_by_name, "created_at": request.created_at,
        "sample_collected_at": request.sample_collected_at,
        "sample_collected_by_name": request.sample_collected_by_name,
        "cancelled_at": request.cancelled_at, "cancel_reason": request.cancel_reason,
        "patient": _patient(patient),
        "admission": {"id": admission.id, "ip_number": admission.ip_number, "status": admission.status.value}
        if admission else None,
        "invoice": {"id": invoice.id, "invoice_number": invoice.invoice_number, "status": invoice.status.value,
                    "total_paise": invoice.total_paise, "paid_paise": invoice.paid_paise,
                    "balance_paise": invoice.total_paise - invoice.paid_paise} if invoice else None,
        "items": items,
        "printable": any(item.status == "verified" for item in request.items),
    }


async def _audit(action: AuditAction, user, http: Request, request: LabRequest, detail: Dict[str, Any]) -> None:
    await audit_record(
        action, actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="lab_request", entity_id=request.id, patient_id=request.patient_id,
        ip_address=client_ip(http), detail={"lab_number": request.lab_number, **detail},
    )


# ------------------------------------------------------------------ options
@router.get("/options", dependencies=[Depends(READ)])
async def options(session: DbSession) -> Dict[str, Any]:
    service = LabService(session)
    groups = [master.name for master in await service.masters(kind="group")] or defaults.GROUPS
    return {
        "groups": groups,
        "master_kinds": list(rules.MASTER_KINDS),
        "result_types": list(rules.RESULT_TYPES),
        "susceptibility": [{"key": key, "label": label} for key, label in rules.SUSCEPTIBILITY.items()],
        "billing_modes": list(rules.BILLING_MODES),
        "priorities": list(rules.PRIORITIES),
    }


# ------------------------------------------------------------------ masters
@router.get("/masters", dependencies=[Depends(READ)])
async def list_masters(
    session: DbSession, kind: Optional[str] = Query(default=None, max_length=16),
    include_inactive: bool = Query(default=False),
) -> List[Dict[str, Any]]:
    return [_master(master) for master in
            await LabService(session).masters(kind=kind, include_inactive=include_inactive)]


@router.post("/masters", status_code=201, dependencies=[Depends(MASTERS)])
async def create_master(payload: MasterIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _master(await LabService(session).save_master(None, payload.model_dump()))
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc


@router.put("/masters/{master_id}", dependencies=[Depends(MASTERS)])
async def update_master(master_id: uuid.UUID, payload: MasterIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _master(await LabService(session).save_master(master_id, payload.model_dump()))
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc


@router.get("/tests", dependencies=[Depends(READ)])
async def list_tests(
    session: DbSession, q: Optional[str] = Query(default=None, max_length=120),
    include_inactive: bool = Query(default=False),
) -> List[Dict[str, Any]]:
    tests = await LabService(session).tests(q=q, include_inactive=include_inactive)
    return [_test(test) for test in tests]


@router.get("/tests/{test_id}", dependencies=[Depends(READ)])
async def get_test(test_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    try:
        return _test(await LabService(session).get_test(test_id))
    except LabError as exc:
        raise _fail(exc) from exc


@router.post("/tests", status_code=201, dependencies=[Depends(MASTERS)])
async def create_test(payload: TestIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _test(await LabService(session).save_test(None, payload.model_dump()))
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc


@router.put("/tests/{test_id}", dependencies=[Depends(MASTERS)])
async def update_test(test_id: uuid.UUID, payload: TestIn, session: DbSession) -> Dict[str, Any]:
    try:
        return _test(await LabService(session).save_test(test_id, payload.model_dump()))
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc


@router.post("/tests/{test_id}/review", dependencies=[Depends(VERIFY)])
async def review_test_ranges(test_id: uuid.UUID, session: DbSession, user: CurrentUser) -> Dict[str, Any]:
    """A doctor confirms the test's ranges match this laboratory's analyser and kits."""
    try:
        return _test(await LabService(session).review_ranges(test_id, user=user))
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc


# ----------------------------------------------------------------- requests
@router.get("/orders/pending", dependencies=[Depends(REGISTER)])
async def pending_orders(session: DbSession) -> List[Dict[str, Any]]:
    return await LabService(session).pending_orders()


@router.get("/requests", dependencies=[Depends(READ)])
async def list_requests(
    session: DbSession,
    q: Optional[str] = Query(default=None, max_length=120),
    status_filter: Optional[str] = Query(default=None, alias="status", max_length=24),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    patient_id: Optional[uuid.UUID] = Query(default=None),
    admission_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
) -> List[Dict[str, Any]]:
    rows = await LabService(session).list_requests(
        q=q, status=status_filter, date_from=date_from, date_to=date_to,
        patient_id=patient_id, admission_id=admission_id, limit=limit,
    )
    now = datetime.now(timezone.utc)
    return [
        {
            "id": request.id, "lab_number": request.lab_number, "status": request.status,
            "billing": request.billing, "priority": request.priority, "referred_by": request.referred_by,
            "created_at": request.created_at, "sample_collected_at": request.sample_collected_at,
            "hours_waiting": round((now - request.created_at).total_seconds() / 3600, 1),
            "patient": _patient(patient),
            "tests": [{"id": item.id, "name": item.name, "status": item.status}
                      for item in sorted(request.items, key=lambda entry: entry.position)],
        }
        for request, patient in rows
    ]


@router.post("/requests", status_code=201, dependencies=[Depends(REGISTER)])
async def register_tests(payload: RegisterIn, session: DbSession, user: CurrentUser, http: Request) -> Dict[str, Any]:
    service = LabService(session)
    try:
        request = await service.register(
            patient_id=payload.patient_id, tests=[line.model_dump() for line in payload.tests],
            billing=payload.billing, admission_id=payload.admission_id,
            consultation_id=payload.consultation_id, order_id=payload.order_id,
            referred_by=payload.referred_by, consultant_id=payload.consultant_id,
            priority=payload.priority, clinical_notes=payload.clinical_notes, user=user,
        )
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.LAB_REGISTER, user, http, request,
                 {"tests": [item.code for item in request.items], "billing": request.billing})
    return await _request(session, service, request, entry=True)


@router.get("/requests/{request_id}", dependencies=[Depends(READ)])
async def get_request(request_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    service = LabService(session)
    try:
        request = await service.get_request(request_id)
    except LabError as exc:
        raise _fail(exc) from exc
    return await _request(session, service, request, entry=True)


@router.post("/requests/{request_id}/collect", dependencies=[Depends(ENTER)])
async def collect_sample(request_id: uuid.UUID, session: DbSession, user: CurrentUser) -> Dict[str, Any]:
    service = LabService(session)
    try:
        await service.collect(request_id, user=user)
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return await _request(session, service, await service.get_request(request_id), entry=True)


@router.post("/requests/{request_id}/bill", dependencies=[Depends(REGISTER)])
async def bill_request(request_id: uuid.UUID, payload: BillIn, session: DbSession, user: CurrentUser) -> Dict[str, Any]:
    service = LabService(session)
    try:
        request = await service.bill_later(request_id, billing=payload.billing,
                                           admission_id=payload.admission_id, user=user)
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return await _request(session, service, request, entry=True)


@router.post("/requests/{request_id}/cancel", dependencies=[Depends(REGISTER)])
async def cancel_tests(
    request_id: uuid.UUID, payload: CancelIn, session: DbSession, user: CurrentUser, http: Request
) -> Dict[str, Any]:
    service = LabService(session)
    try:
        outcome = await service.cancel(request_id, item_ids=payload.item_ids, reason=payload.reason, user=user)
        request = await service.get_request(request_id)
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.LAB_CANCEL, user, http, request,
                 {"reason": payload.reason, "items": [str(item) for item in payload.item_ids or []] or "all",
                  "refund_due_paise": outcome["refund_due_paise"]})
    return {**await _request(session, service, request, entry=True), **outcome}


@router.get("/requests/{request_id}/report", dependencies=[Depends(READ)])
async def print_report(request_id: uuid.UUID, session: DbSession, user: CurrentUser, http: Request) -> Response:
    service = LabService(session)
    try:
        request = await service.get_request(request_id)
    except LabError as exc:
        raise _fail(exc) from exc
    if not any(item.status == "verified" for item in request.items):
        raise HTTPException(status.HTTP_409_CONFLICT, "No result on this request has been verified yet.")
    patient = await session.get(Patient, request.patient_id)
    admission = await session.get(Admission, request.admission_id) if request.admission_id else None
    pdf = await asyncio.to_thread(render_lab_report, request=request, items=list(request.items), patient=patient,
                                  admission=admission, layout=await load_layout(session, "lab_report"))
    await _audit(AuditAction.EXPORT_DOCUMENT, user, http, request, {"document": "lab_report"})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{request.lab_number}.pdf"'})


# ------------------------------------------------------------------ results
@router.post("/items/{item_id}/results", dependencies=[Depends(ENTER)])
async def save_results(item_id: uuid.UUID, payload: ResultsIn, session: DbSession, user: CurrentUser) -> Dict[str, Any]:
    service = LabService(session)
    try:
        item = await service.save_results(item_id, values=payload.values, prints=payload.prints,
                                          remarks=payload.remarks, culture=payload.culture, user=user)
        request = await service.get_request(item.request_id)
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    return await _request(session, service, request, entry=True)


@router.post("/items/{item_id}/verify", dependencies=[Depends(VERIFY)])
async def verify_result(
    item_id: uuid.UUID, payload: VerifyIn, session: DbSession, user: CurrentUser, http: Request
) -> Dict[str, Any]:
    service = LabService(session)
    try:
        item = await service.verify(item_id, critical_note=payload.critical_note, user=user)
        request = await service.get_request(item.request_id)
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.LAB_VERIFY, user, http, request,
                 {"test": item.code, "version": item.version,
                  "critical": [row["name"] for row in rules.critical_rows(item.results or [])]})
    return await _request(session, service, request, entry=True)


@router.post("/items/{item_id}/reopen", dependencies=[Depends(VERIFY)])
async def reopen_result(
    item_id: uuid.UUID, payload: ReasonIn, session: DbSession, user: CurrentUser, http: Request
) -> Dict[str, Any]:
    service = LabService(session)
    try:
        item = await service.reopen(item_id, reason=payload.reason, user=user)
        request = await service.get_request(item.request_id)
    except LabError as exc:
        await session.rollback()
        raise _fail(exc) from exc
    await _audit(AuditAction.LAB_REOPEN, user, http, request,
                 {"test": item.code, "version": item.version, "reason": payload.reason})
    return await _request(session, service, request, entry=True)


@router.post("/items/{item_id}/printout", dependencies=[Depends(ENTER)])
async def read_printout(item_id: uuid.UUID, session: DbSession, file: UploadFile = File(...)) -> Dict[str, Any]:
    """Suggested values from an analyser printout. Nothing is saved."""
    content_type = (file.content_type or "").lower()
    if content_type not in PRINTOUT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload the printout as a PDF, PNG or JPEG.")
    limit = settings.MAX_REPORT_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"File is larger than the {settings.MAX_REPORT_UPLOAD_MB} MB limit.")
    try:
        return await LabService(session).read_printout(item_id, data=data, content_type=content_type,
                                                       filename=file.filename or "printout")
    except LabError as exc:
        raise _fail(exc) from exc


@router.get("/patients/{patient_id}/context", dependencies=[Depends(REGISTER)])
async def patient_context(patient_id: uuid.UUID, session: DbSession) -> Dict[str, Any]:
    """The patient and their current admission, so tests can be billed to the stay."""
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    admission = (await session.execute(
        select(Admission).where(
            Admission.patient_id == patient_id,
            Admission.status.notin_([AdmissionStatus.DISCHARGED, AdmissionStatus.CANCELLED]),
        ).order_by(Admission.admitted_at.desc())
    )).scalars().first()
    return {
        "patient": _patient(patient),
        "admission": {"id": admission.id, "ip_number": admission.ip_number,
                      "billable": admission.final_invoice_id is None} if admission else None,
    }


@router.get("/patients/{patient_id}/results", dependencies=[Depends(READ)])
async def patient_results(
    patient_id: uuid.UUID, session: DbSession, admission_id: Optional[uuid.UUID] = Query(default=None)
) -> List[Dict[str, Any]]:
    """Verified results for one patient, newest first — what a doctor reads."""
    rows = await LabService(session).patient_results(patient_id, admission_id=admission_id)
    return [
        {**_item(item), "request_id": request.id, "lab_number": request.lab_number,
         "registered_at": request.created_at, "referred_by": request.referred_by}
        for item, request in rows
    ]
