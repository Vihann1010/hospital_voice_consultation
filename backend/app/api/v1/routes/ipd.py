"""Inpatient ward: admission, bed board, chart, charges, discharge."""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, get_ipd_service, require_permission
from app.core.permissions import Permission, has_permission
from app.core.audit import client_ip, record as audit_record
from app.core.logging import get_logger
from app.models.enums import (
    AuditAction, ChargeCategory, Department, MedicationStatus, NoteType, UserRole,
)
from app.models.ipd import (
    Admission, Bed, BedOccupancy, ClinicalNote, MedicationAdministration,
    MedicationOrder, Ward,
)
from app.models.patient import Patient
from app.schemas.ipd_schemas import (
    AdmissionOut, AdministerRequest, AdmitRequest, BedStatusUpdate, BedUpsert,
    ChargeOut, ChargeRequest, DischargeRequest, MedicationOrderOut,
    MedicationOrderRequest, NoteOut, NoteRequest, ReviewSummaryRequest,
    TransferRequest, VitalsOut, VitalsRequest, WardUpsert,
)
from app.services.ipd_service import IPDError, IPDService
from app.core.clock import local_today
from app.schemas.drug_chart_schemas import DrugCheckIn, DrugOrderIn, GiveNowIn
from app.services.drug_chart_service import DrugChartError, DrugChartService

logger = get_logger(__name__)
router = APIRouter(prefix="/ipd", tags=["ipd"])

Service = Annotated[IPDService, Depends(get_ipd_service)]

# Reading the ward — the board, a chart, a running bill — is everyday work
# for anyone who can open a patient.
WARD_READ = require_permission(Permission.PATIENT_READ)
# Writing on it — observations, doses, bed moves, charges — is ward charting.
# It used to sit behind the read permission, so any account could record a
# patient's blood pressure. It is not clinical authority, but it is not
# nothing either.
WARD = require_permission(Permission.WARD_CHART)
# Admitting, discharging, prescribing and diagnosing are the doctor's.
CLINICAL = require_permission(Permission.CONSULTATION_REVIEW)


# --------------------------------------------------------------- ward board
@router.get("/board", dependencies=[Depends(WARD_READ)])
async def ward_board(
    service: Service, department: Optional[Department] = Query(default=None)
) -> Dict[str, Any]:
    """Every ward, every bed, and who is in it."""
    return {"wards": await service.ward_board(department=department)}


@router.get("/census", dependencies=[Depends(WARD_READ)])
async def census(service: Service) -> Dict[str, Any]:
    return await service.census()


@router.post("/wards", dependencies=[Depends(CLINICAL)], status_code=201)
async def create_ward(payload: WardUpsert, session: DbSession) -> Dict[str, Any]:
    existing = await session.execute(select(Ward).where(Ward.code == payload.code))
    ward = existing.scalar_one_or_none()
    if ward is None:
        ward = Ward(**payload.model_dump())
        session.add(ward)
    else:
        for field, value in payload.model_dump().items():
            setattr(ward, field, value)
    await session.commit()
    return {"id": str(ward.id), "code": ward.code, "name": ward.name}


@router.post("/beds", dependencies=[Depends(CLINICAL)], status_code=201)
async def create_bed(payload: BedUpsert, session: DbSession) -> Dict[str, Any]:
    bed = Bed(**payload.model_dump())
    session.add(bed)
    await session.commit()
    return {"id": str(bed.id), "label": bed.label, "status": bed.status.value}


@router.patch("/beds/{bed_id}/status", dependencies=[Depends(WARD)])
async def set_bed_status(
    bed_id: uuid.UUID, payload: BedStatusUpdate, session: DbSession
) -> Dict[str, Any]:
    """Mark a bed cleaned, blocked or under maintenance.

    Refuses while a patient is in it: freeing an occupied bed here is how a
    ward ends up assigning a bed that is not actually empty.
    """
    bed = await session.get(Bed, bed_id)
    if bed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bed not found")

    from sqlalchemy import func

    open_count = await session.execute(
        select(func.count()).select_from(BedOccupancy).where(
            BedOccupancy.bed_id == bed_id, BedOccupancy.ended_at.is_(None)
        )
    )
    if int(open_count.scalar_one()) > 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "There is still a patient in this bed. Discharge or transfer them first.",
        )

    bed.status = payload.status
    if payload.notes is not None:
        bed.notes = payload.notes
    await session.commit()
    return {"id": str(bed.id), "status": bed.status.value}


# ---------------------------------------------------------------- admission
@router.post("/admissions", response_model=AdmissionOut, status_code=201,
             dependencies=[Depends(CLINICAL)])
async def admit(
    payload: AdmitRequest, service: Service, user: CurrentUser, request: Request
) -> AdmissionOut:
    if payload.advance_paid_paise > 0 and not has_permission(user.role, Permission.PAYMENT_COLLECT):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Taking an advance needs permission to collect payment.")
    try:
        admission = await service.admit(
            **payload.model_dump(), admitted_by_name=user.full_name
        )
        await service.session.commit()
    except IPDError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.CREATE_ORDER,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="admission", entity_id=admission.id,
        patient_id=admission.patient_id, ip_address=client_ip(request),
        detail={"ip_number": admission.ip_number,
                "advance_receipt": getattr(admission, "advance_receipt_number", None)},
    )
    return AdmissionOut.model_validate(admission)


@router.get("/admissions", response_model=List[AdmissionOut], dependencies=[Depends(WARD_READ)])
async def active_admissions(
    service: Service, department: Optional[Department] = Query(default=None)
) -> List[AdmissionOut]:
    rows = await service.active_admissions(department=department)
    return [AdmissionOut.model_validate(row) for row in rows]


@router.get("/admissions/{admission_id}", dependencies=[Depends(WARD_READ)])
async def admission_chart(admission_id: uuid.UUID, service: Service) -> Dict[str, Any]:
    """The whole bedside chart in one call.

    Deliberately one round trip: a ward tablet on hospital wifi should not
    need six requests to render a patient.
    """
    admission = await service.get_admission(admission_id)
    if admission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admission not found")

    patient = await service.session.get(Patient, admission.patient_id)
    current = next((o for o in admission.occupancies if o.ended_at is None), None)

    return {
        "admission": AdmissionOut.model_validate(admission).model_dump(),
        "patient": {
            "id": str(patient.id), "uhid": patient.uhid, "name": patient.name,
            "age": patient.age, "gender": patient.gender.value,
            "phone_number": patient.phone_number,
            "blood_group": patient.blood_group,
        } if patient else None,
        "current_bed": {
            "ward": current.ward_name, "bed": current.bed_label,
            "since": current.started_at.isoformat(),
        } if current else None,
        "occupancies": [
            {"ward": o.ward_name, "bed": o.bed_label,
             "from": o.started_at.isoformat(),
             "to": o.ended_at.isoformat() if o.ended_at else None,
             "reason": o.transfer_reason}
            for o in admission.occupancies
        ],
        "vitals": [VitalsOut.model_validate(v).model_dump() for v in admission.vitals],
        "medications": [
            MedicationOrderOut.model_validate(m).model_dump()
            for m in admission.medications
        ],
        "notes": [NoteOut.model_validate(n).model_dump() for n in admission.notes],
        "bill": await service.running_bill(admission_id),
        "leaves": [_leave_out(leave) for leave in await service.leaves(admission_id)],
        "readmission_of": await service.readmission_summary(admission),
    }


@router.post("/admissions/{admission_id}/transfer", dependencies=[Depends(WARD)])
async def transfer(
    admission_id: uuid.UUID, payload: TransferRequest, service: Service,
    user: CurrentUser,
) -> Dict[str, Any]:
    try:
        occupancy = await service.transfer(
            admission_id=admission_id, to_bed_id=payload.to_bed_id,
            reason=payload.reason, moved_by_name=user.full_name,
        )
        await service.session.commit()
    except IPDError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ward": occupancy.ward_name, "bed": occupancy.bed_label,
            "since": occupancy.started_at.isoformat()}


# ------------------------------------------------------------------- vitals
@router.post("/admissions/{admission_id}/vitals", dependencies=[Depends(WARD)])
async def record_vitals(
    admission_id: uuid.UUID, payload: VitalsRequest, service: Service,
    user: CurrentUser,
) -> Dict[str, Any]:
    """Record observations. The early warning score is returned immediately.

    Scored on the server, deterministically, so the nurse sees the escalation
    the instant the numbers are entered — no model, no network dependency.
    """
    try:
        record, score = await service.record_vitals(
            admission_id=admission_id, recorded_by_id=user.id,
            recorded_by_name=user.full_name, **payload.model_dump(),
        )
        await service.session.commit()
    except IPDError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return {"vitals": VitalsOut.model_validate(record).model_dump(), "news2": score}


@router.get("/alerts/deteriorating", dependencies=[Depends(WARD_READ)])
async def deteriorating(
    service: Service,
    department: Optional[Department] = Query(default=None),
    threshold: int = Query(default=5, ge=1, le=20),
) -> Dict[str, Any]:
    """Everyone currently scoring at or above the escalation threshold."""
    patients = await service.deteriorating_patients(
        department=department, threshold=threshold
    )
    return {"threshold": threshold, "count": len(patients), "patients": patients}


# -------------------------------------------------------------- medications
# --------------------------------------------------------------- drug chart
def _chart_error(exc: DrugChartError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.post("/admissions/{admission_id}/medications/check", dependencies=[Depends(CLINICAL)])
async def check_medication(
    admission_id: uuid.UUID, payload: DrugCheckIn, session: DbSession
) -> Dict[str, Any]:
    """The safety alerts a new order would raise, before it is placed."""
    try:
        return await DrugChartService(session).check(admission_id, drug_name=payload.drug_name)
    except DrugChartError as exc:
        raise _chart_error(exc) from exc


@router.post("/admissions/{admission_id}/medications", response_model=MedicationOrderOut,
             status_code=201, dependencies=[Depends(CLINICAL)])
async def order_medication(
    admission_id: uuid.UUID, payload: DrugOrderIn, session: DbSession, user: CurrentUser,
) -> MedicationOrderOut:
    """Prescribe a medicine for the stay and lay out its doses.

    Checked for allergies, duplicates and interactions against the admission,
    the same way an OPD prescription is. Doses are scheduled in hospital time
    from the frequency's round times unless explicit times are given.
    """
    try:
        order = await DrugChartService(session).order(
            admission_id,
            payload=payload.model_dump(exclude={"acknowledged_alerts"}),
            acknowledged=payload.acknowledged_alerts,
            user=user,
        )
    except DrugChartError as exc:
        await session.rollback()
        raise _chart_error(exc) from exc
    return MedicationOrderOut.model_validate(order)


@router.get("/admissions/{admission_id}/drug-chart", dependencies=[Depends(WARD_READ)])
async def drug_chart(
    admission_id: uuid.UUID, session: DbSession, on: Optional[date] = Query(default=None),
) -> Dict[str, Any]:
    """One day of the drug chart. Tops up the dose schedule as it reads."""
    try:
        return await DrugChartService(session).chart(admission_id, on or local_today())
    except DrugChartError as exc:
        raise _chart_error(exc) from exc


@router.post("/medications/{administration_id}/administer", dependencies=[Depends(WARD)])
async def administer(
    administration_id: uuid.UUID, payload: AdministerRequest, session: DbSession,
    user: CurrentUser,
) -> Dict[str, Any]:
    """Sign for a dose — given, or not given with a reason.

    An omission must carry a reason: a dose not given is as clinically
    significant as one given, and a blank is indistinguishable from a dose
    nobody got round to signing.
    """
    try:
        dose = await DrugChartService(session).administer(
            administration_id, was_given=payload.was_given,
            omission_reason=payload.omission_reason, notes=payload.notes, user=user,
        )
    except DrugChartError as exc:
        await session.rollback()
        raise _chart_error(exc) from exc
    return {"id": str(dose.id), "was_given": dose.was_given,
            "given_at": dose.given_at.isoformat()}


@router.post("/medications/{order_id}/give", dependencies=[Depends(WARD)])
async def give_as_needed(
    order_id: uuid.UUID, session: DbSession, user: CurrentUser,
    payload: Optional[GiveNowIn] = None,
) -> Dict[str, Any]:
    """Record a when-needed (SOS) dose given now."""
    try:
        dose = await DrugChartService(session).give_as_needed(
            order_id, notes=payload.notes if payload else None, user=user
        )
    except DrugChartError as exc:
        await session.rollback()
        raise _chart_error(exc) from exc
    return {"id": str(dose.id), "given_at": dose.given_at.isoformat()}


@router.post("/medications/{order_id}/stop", dependencies=[Depends(CLINICAL)])
async def stop_medication(
    order_id: uuid.UUID, session: DbSession, user: CurrentUser,
    reason: str = Query(..., min_length=2),
) -> Dict[str, Any]:
    try:
        order = await DrugChartService(session).stop(order_id, reason=reason, user=user)
    except DrugChartError as exc:
        await session.rollback()
        raise _chart_error(exc) from exc
    return {"id": str(order.id), "status": order.status.value}


# -------------------------------------------------------------------- notes
@router.post("/admissions/{admission_id}/notes", response_model=NoteOut,
             status_code=201, dependencies=[Depends(WARD)])
async def add_note(
    admission_id: uuid.UUID, payload: NoteRequest, session: DbSession,
    user: CurrentUser,
) -> NoteOut:
    note = ClinicalNote(
        admission_id=admission_id, author_id=user.id, author_name=user.full_name,
        author_role=user.role.value, **payload.model_dump(),
    )
    session.add(note)
    await session.commit()
    return NoteOut.model_validate(note)


# ------------------------------------------------------------------ charges
@router.post("/admissions/{admission_id}/charges", response_model=ChargeOut,
             status_code=201, dependencies=[Depends(WARD)])
async def post_charge(
    admission_id: uuid.UUID, payload: ChargeRequest, service: Service,
    user: CurrentUser,
) -> ChargeOut:
    try:
        charge = await service.post_charge(
            admission_id=admission_id, posted_by_name=user.full_name,
            **payload.model_dump(),
        )
        await service.session.commit()
    except IPDError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ChargeOut.model_validate(charge)


@router.get("/admissions/{admission_id}/bill", dependencies=[Depends(WARD_READ)])
async def running_bill(admission_id: uuid.UUID, service: Service) -> Dict[str, Any]:
    """What the stay has cost so far — the question families ask daily."""
    try:
        return await service.running_bill(admission_id)
    except IPDError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/admissions/{admission_id}/accrue", dependencies=[Depends(WARD)])
async def accrue(admission_id: uuid.UUID, service: Service) -> Dict[str, Any]:
    """Post any bed-days not yet charged. Safe to call repeatedly."""
    try:
        posted = await service.accrue_bed_charges(admission_id)
        await service.session.commit()
    except IPDError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"posted": len(posted),
            "bill": await service.running_bill(admission_id)}

# ----------------------------------------------------------- final billing
@router.post("/admissions/{admission_id}/invoice", dependencies=[Depends(WARD)])
async def raise_final_invoice(
    admission_id: uuid.UUID,
    service: Service,
    user: CurrentUser,
    discount_paise: int = Query(default=0, ge=0),
    discount_reason: Optional[str] = Query(default=None),
    payer_covered_paise: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """Raise the discharge bill from everything accrued during the stay.

    Charges are grouped by category, the admission advance is set against the
    total, and the result is a numbered invoice in the same sequence as OPD —
    so the day's finance figures include inpatients rather than quietly
    omitting them.
    """
    try:
        # Sweep anything not yet posted before billing, or the last night in
        # a bed is missed on every discharge.
        await service.accrue_bed_charges(admission_id, posted_by_name=user.full_name)
        invoice, summary = await service.finalise_billing(
            admission_id,
            discount_paise=discount_paise,
            discount_reason=discount_reason,
            payer_covered_paise=payer_covered_paise,
            created_by_name=user.full_name,
        )
        await service.session.commit()
    except IPDError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    from app.schemas.emr_schemas import InvoiceOut
    return {"invoice": InvoiceOut.model_validate(invoice).model_dump(), **summary}


@router.get("/patients/search", dependencies=[Depends(WARD_READ)])
async def search_patients_for_admission(
    session: DbSession,
    q: str = Query(..., min_length=1, max_length=120),
) -> List[Dict[str, Any]]:
    """Find an existing patient to admit.

    The ward needs this for the same reason reception does: admitting someone
    who is already in the system as a new patient splits their history across
    two records, and the second one has none of their allergies.
    """
    from app.services.reception_service import ReceptionService

    found = await ReceptionService(session).find_patients(q)
    return [
        {"id": str(p.id), "uhid": p.uhid, "name": p.name, "age": p.age,
         "gender": p.gender.value, "phone_number": p.phone_number,
         "blood_group": p.blood_group}
        for p in found
    ]


@router.post("/patients", dependencies=[Depends(WARD)], status_code=201)
async def register_patient_for_admission(
    payload: Dict[str, Any], session: DbSession
) -> Dict[str, Any]:
    """Register a patient who arrives straight onto the ward.

    An emergency admission does not pass the OPD counter, so the ward has to
    be able to create the record — with a real UHID, through the same
    allocator reception uses, not a second numbering scheme.
    """
    from app.models.enums import Gender
    from app.services.reception_service import ReceptionError, ReceptionService

    service = ReceptionService(session)
    try:
        patient = await service.register_patient(
            name=str(payload.get("name") or "").strip(),
            age=int(payload.get("age") or 0),
            gender=Gender(str(payload.get("gender") or "other")),
            phone_number=str(payload.get("phone_number") or "").strip(),
            address=payload.get("address"),
            city=payload.get("city"),
            blood_group=payload.get("blood_group"),
            emergency_contact_name=payload.get("emergency_contact_name"),
            emergency_contact_phone=payload.get("emergency_contact_phone"),
        )
        await session.commit()
    except (ReceptionError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"id": str(patient.id), "uhid": patient.uhid, "name": patient.name,
            "age": patient.age, "gender": patient.gender.value,
            "phone_number": patient.phone_number}

# ---------------------------------------------------------------- discharge
@router.post("/admissions/{admission_id}/discharge/initiate",
             dependencies=[Depends(CLINICAL)])
async def initiate_discharge(
    admission_id: uuid.UUID, service: Service,
    final_diagnosis: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Write the patient up for discharge. The bed is not released yet."""
    try:
        admission = await service.initiate_discharge(
            admission_id, final_diagnosis=final_diagnosis
        )
        await service.session.commit()
    except IPDError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ip_number": admission.ip_number, "status": admission.status.value}


@router.post("/admissions/{admission_id}/discharge", dependencies=[Depends(CLINICAL)])
async def complete_discharge(
    admission_id: uuid.UUID, payload: DischargeRequest, service: Service,
    user: CurrentUser, request: Request,
) -> Dict[str, Any]:
    """Close the stay: final accrual, release the bed, stop the drug chart."""
    try:
        admission, bill = await service.complete_discharge(
            admission_id, discharge_type=payload.discharge_type,
            final_diagnosis=payload.final_diagnosis,
            discharged_by_name=user.full_name,
        )
        await service.session.commit()
    except IPDError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_record(
        AuditAction.EXPORT_DOCUMENT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="discharge", entity_id=admission.id,
        patient_id=admission.patient_id, ip_address=client_ip(request),
        detail={"ip_number": admission.ip_number,
                "type": payload.discharge_type.value,
                "total_paise": bill["total_paise"]},
    )
    return {"admission": AdmissionOut.model_validate(admission).model_dump(),
            "bill": bill}


# ----------------------------------------------------------------------- AI
@router.post("/admissions/{admission_id}/ai/discharge-summary",
             dependencies=[Depends(CLINICAL)])
async def draft_discharge_summary(
    admission_id: uuid.UUID, service: Service, user: CurrentUser
) -> Dict[str, Any]:
    """Draft a discharge summary from the stay record.

    The draft is saved unsigned and flagged as AI-written. It is not a
    discharge summary until a doctor reviews it — the endpoint that accepts
    it is separate, deliberately.
    """
    from app.ai.ipd_documentation import (
        DischargeSummaryService, build_stay_record, render_discharge_summary,
    )
    from app.ai.pipeline.base_service import StageError

    admission = await service.get_admission(admission_id)
    if admission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admission not found")
    patient = await service.session.get(Patient, admission.patient_id)

    record = build_stay_record(
        patient={"name": patient.name, "age": patient.age,
                 "gender": patient.gender.value, "uhid": patient.uhid} if patient else {},
        admission={
            "ip_number": admission.ip_number,
            "admitted_at": admission.admitted_at.isoformat(),
            "discharged_at": admission.discharged_at.isoformat()
            if admission.discharged_at else None,
            "admitting_doctor_name": admission.admitting_doctor_name,
            "reason_for_admission": admission.reason_for_admission,
            "provisional_diagnosis": admission.provisional_diagnosis,
            "final_diagnosis": admission.final_diagnosis,
            "allergies": admission.allergies or [],
        },
        occupancies=[
            {"ward_name": o.ward_name, "bed_label": o.bed_label,
             "started_at": o.started_at.isoformat(),
             "ended_at": o.ended_at.isoformat() if o.ended_at else None}
            for o in admission.occupancies
        ],
        vitals=[
            {"recorded_at": v.recorded_at.isoformat(),
             "respiratory_rate": v.respiratory_rate, "spo2_percent": v.spo2_percent,
             "systolic_bp": v.systolic_bp, "pulse": v.pulse,
             "temperature_c": v.temperature_c, "news2_score": v.news2_score,
             "news2_risk": v.news2_risk}
            for v in admission.vitals
        ],
        notes=[
            {"created_at": n.created_at.isoformat(), "note_type": n.note_type.value,
             "author_name": n.author_name, "content": n.content}
            for n in admission.notes
        ],
        medications=[
            {"drug_name": m.drug_name, "strength": m.strength, "dose": m.dose,
             "route": m.route.value, "frequency_code": m.frequency_code,
             "status": m.status.value, "instructions": m.instructions}
            for m in admission.medications
        ],
    )

    try:
        draft = await DischargeSummaryService().draft(record, tag=admission.ip_number)
    except StageError as exc:
        # The stay record is still returned so the doctor can write the
        # summary themselves rather than being blocked by a model outage.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The summary could not be drafted right now ({exc}). "
            "The full stay record is available on the chart.",
        ) from exc

    rendered = render_discharge_summary(draft)
    note = ClinicalNote(
        admission_id=admission_id, note_type=NoteType.DISCHARGE_SUMMARY,
        author_id=user.id, author_name=user.full_name, author_role=user.role.value,
        content=rendered, ai_generated=True,
    )
    service.session.add(note)
    await service.session.commit()

    return {
        "note_id": str(note.id),
        "content": rendered,
        "structured": draft.model_dump(),
        "requires_review": True,
        "notice": "Drafted by AI from the ward record. Review every line, "
                  "especially the medicines, before signing.",
    }


@router.post("/notes/{note_id}/review", response_model=NoteOut,
             dependencies=[Depends(CLINICAL)])
async def review_ai_note(
    note_id: uuid.UUID, payload: ReviewSummaryRequest, session: DbSession,
    user: CurrentUser,
) -> NoteOut:
    """A clinician accepts an AI draft, with whatever edits they made.

    A new note supersedes the draft rather than overwriting it: what the model
    produced and what the doctor signed are both preserved, which is the point
    of flagging AI authorship in the first place.
    """
    original = await session.get(ClinicalNote, note_id)
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")

    signed = ClinicalNote(
        admission_id=original.admission_id, note_type=original.note_type,
        author_id=user.id, author_name=user.full_name, author_role=user.role.value,
        content=payload.content, ai_generated=True,
        ai_reviewed_by_name=user.full_name,
        ai_reviewed_at=datetime.now(timezone.utc), supersedes_id=original.id,
    )
    session.add(signed)
    await session.commit()
    return NoteOut.model_validate(signed)


@router.post("/admissions/{admission_id}/ai/handover", dependencies=[Depends(WARD)])
async def draft_handover(admission_id: uuid.UUID, service: Service) -> Dict[str, Any]:
    """A ninety-second handover for the incoming shift."""
    from app.ai.ipd_documentation import HandoverService, build_stay_record
    from app.ai.pipeline.base_service import StageError

    admission = await service.get_admission(admission_id)
    if admission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admission not found")
    patient = await service.session.get(Patient, admission.patient_id)

    record = build_stay_record(
        patient={"name": patient.name, "age": patient.age,
                 "gender": patient.gender.value, "uhid": patient.uhid} if patient else {},
        admission={"ip_number": admission.ip_number,
                   "admitted_at": admission.admitted_at.isoformat(),
                   "admitting_doctor_name": admission.admitting_doctor_name,
                   "provisional_diagnosis": admission.provisional_diagnosis,
                   "allergies": admission.allergies or []},
        occupancies=[],
        vitals=[{"recorded_at": v.recorded_at.isoformat(),
                 "respiratory_rate": v.respiratory_rate, "spo2_percent": v.spo2_percent,
                 "systolic_bp": v.systolic_bp, "pulse": v.pulse,
                 "temperature_c": v.temperature_c, "news2_score": v.news2_score,
                 "news2_risk": v.news2_risk} for v in admission.vitals[-12:]],
        notes=[{"created_at": n.created_at.isoformat(), "note_type": n.note_type.value,
                "author_name": n.author_name, "content": n.content}
               for n in admission.notes[-6:]],
        medications=[{"drug_name": m.drug_name, "dose": m.dose, "route": m.route.value,
                      "frequency_code": m.frequency_code, "status": m.status.value}
                     for m in admission.medications
                     if m.status == MedicationStatus.ACTIVE],
    )
    try:
        draft = await HandoverService().draft(record, tag=admission.ip_number)
    except StageError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The handover could not be drafted right now ({exc}).",
        ) from exc
    return draft.model_dump()


# -------------------------------------------------------------------- leave
from datetime import date as _date  # noqa: E402

from pydantic import BaseModel as _Model, Field as _Field  # noqa: E402

CHARGES_ADMIN = require_permission(Permission.MASTER_MANAGE)


class LeaveRequest(_Model):
    reason: str = _Field(min_length=3, max_length=1000)
    expected_return_on: Optional[_date] = None
    bed_retained: bool = True


class ReturnRequest(_Model):
    bed_id: Optional[uuid.UUID] = None
    note: Optional[str] = _Field(default=None, max_length=1000)


def _leave_out(leave) -> Dict[str, Any]:
    return {
        "id": str(leave.id),
        "started_at": leave.started_at.isoformat(),
        "expected_return_on": leave.expected_return_on.isoformat() if leave.expected_return_on else None,
        "reason": leave.reason,
        "bed_retained": leave.bed_retained,
        "released_bed": f"{leave.released_ward_name} {leave.released_bed_label}" if leave.released_bed_label else None,
        "started_by_name": leave.started_by_name,
        "returned_at": leave.returned_at.isoformat() if leave.returned_at else None,
        "returned_by_name": leave.returned_by_name,
        "return_note": leave.return_note,
    }


@router.post("/admissions/{admission_id}/leave", dependencies=[Depends(WARD)])
async def start_leave(
    admission_id: uuid.UUID, payload: LeaveRequest, service: Service, user: CurrentUser, request: Request
) -> Dict[str, Any]:
    """Send the patient home on leave. They stay admitted; the bed is kept unless released."""
    try:
        leave = await service.start_leave(
            admission_id, reason=payload.reason, expected_return_on=payload.expected_return_on,
            bed_retained=payload.bed_retained, started_by_name=user.full_name,
        )
        await service.session.commit()
    except IPDError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    admission = await service.session.get(Admission, admission_id)
    await audit_record(
        AuditAction.LEAVE_START,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="admission", entity_id=admission_id, patient_id=admission.patient_id if admission else None,
        ip_address=client_ip(request),
        detail={"bed_retained": payload.bed_retained, "reason": payload.reason,
                "expected_return_on": payload.expected_return_on.isoformat() if payload.expected_return_on else None},
    )
    return _leave_out(leave)


@router.post("/admissions/{admission_id}/return", dependencies=[Depends(WARD)])
async def end_leave(
    admission_id: uuid.UUID, payload: ReturnRequest, service: Service, user: CurrentUser, request: Request
) -> Dict[str, Any]:
    """The patient is back from leave."""
    try:
        leave, missed = await service.end_leave(
            admission_id, bed_id=payload.bed_id, note=payload.note, returned_by_name=user.full_name
        )
        await service.session.commit()
    except IPDError as exc:
        await service.session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    admission = await service.session.get(Admission, admission_id)
    await audit_record(
        AuditAction.LEAVE_RETURN,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="admission", entity_id=admission_id, patient_id=admission.patient_id if admission else None,
        ip_address=client_ip(request), detail={"missed_doses_recorded": missed},
    )
    return {**_leave_out(leave), "missed_doses_recorded": missed}


# ------------------------------------------------------------ room charges
def _run_out(run) -> Dict[str, Any]:
    return {
        "id": str(run.id), "run_on": run.run_on.isoformat(), "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "summary": run.summary or {}, "error": run.error, "triggered_by": run.triggered_by,
    }


@router.get("/room-charges/runs", dependencies=[Depends(WARD_READ)])
async def room_charge_runs(service: Service, limit: int = Query(default=14, ge=1, le=90)) -> Dict[str, Any]:
    """The recent morning room-charge runs, newest first."""
    from app.core.config import settings
    from app.ipd.room_charges import JOB
    from app.models.job_run import JobRun

    from sqlalchemy import select as _select

    runs = (await service.session.execute(
        _select(JobRun).where(JobRun.job == JOB).order_by(JobRun.started_at.desc()).limit(limit)
    )).scalars().all()
    return {"run_at": settings.BED_CHARGE_RUN_AT, "enabled": settings.BED_CHARGE_WORKER_ENABLED,
            "runs": [_run_out(run) for run in runs]}


@router.post("/room-charges/run", dependencies=[Depends(CHARGES_ADMIN)])
async def run_room_charges_now(user: CurrentUser, request: Request) -> Dict[str, Any]:
    """Post room charges now. Safe to repeat: days already charged are skipped."""
    from app.ipd.room_charges import run_room_charges

    run = await run_room_charges(triggered_by=user.full_name)
    await audit_record(
        AuditAction.ROOM_CHARGES_RUN,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="job_run", entity_id=run.id, ip_address=client_ip(request),
        detail={"status": run.status, **{k: v for k, v in (run.summary or {}).items() if k != "failed"}},
    )
    return _run_out(run)

