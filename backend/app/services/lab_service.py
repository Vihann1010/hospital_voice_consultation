"""The laboratory: the test list, registering tests, results, verification.

The rules about a single value — is it a number, which range applies, is it
flagged, can this test be verified — are in `app/lab/rules.py`. This service
adds the hospital around them:

* **A request is billed when it is registered**, from each test's price code:
  on a counter bill, or to the patient's admission. A test with no price code
  is refused rather than billed at nothing; it can still be registered
  unbilled for the counter to charge later.
* **Results need a collected sample**, and a verified result needs a doctor,
  a reviewed test, and — for a critical value — a record of who was told.
* **Cancelling never loses money silently.** An unpaid bill is corrected or
  cancelled with the test; a paid one is left as it is and the refund due is
  reported, because returning money is the counter's act, not the lab's.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import day_bounds, local_today
from app.core.logging import get_logger
from app.core.permissions import Permission, has_permission
from app.lab import rules
from app.models.consultant import Consultant
from app.models.emr import DocumentCounter, Invoice, InvoiceLine, ServiceItem
from app.models.enums import AdmissionStatus, ChargeCategory, InvoiceStatus, OrderStatus
from app.models.investigation import InvestigationOrder, InvestigationOrderItem
from app.models.ipd import Admission, AdmissionCharge
from app.models.lab import LabMaster, LabParameter, LabRequest, LabRequestItem, LabTest
from app.models.patient import Patient
from app.models.user import User

logger = get_logger(__name__)

# Order categories the laboratory may be asked for. Orthopaedic and
# gynaecology orders also contain imaging and procedures, so from those only
# items whose code a lab test claims are shown.
LAB_CATEGORIES = {"blood", "urine", "hormonal", "tumor_markers"}
MIXED_CATEGORIES = {"orthopedic", "gynecology"}

PRINTOUT_UNCLEAR = "Printout unclear, please enter the results manually."

_PARAMETER_FIELDS = ("position", "name", "analyte_key", "aliases", "result_type", "unit", "method",
                     "choices", "normal_values", "ranges", "range_text", "print_default", "is_active")


class LabError(Exception):
    """A laboratory request that cannot be honoured, with a reason to show."""

    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def patient_sex(patient: Patient) -> Optional[str]:
    value = getattr(patient.gender, "value", patient.gender)
    return value if value in ("male", "female") else None


def parameter_dict(parameter: LabParameter) -> Dict[str, Any]:
    return {
        "id": str(parameter.id),
        "position": parameter.position,
        "name": parameter.name,
        "analyte_key": parameter.analyte_key,
        "aliases": list(parameter.aliases or []),
        "result_type": parameter.result_type,
        "unit": parameter.unit,
        "method": parameter.method,
        "choices": list(parameter.choices or []),
        "normal_values": list(parameter.normal_values or []),
        "ranges": list(parameter.ranges or []),
        "range_text": parameter.range_text,
        "print_default": parameter.print_default,
        "is_active": parameter.is_active,
    }


def _clinical_signature(parameters: List[LabParameter]) -> str:
    """What a pathologist signs off when reviewing a test. A change to any of
    it — a range, a unit, the choices counted as normal — needs a new review;
    renaming a line or moving it does not."""
    entries = {
        str(parameter.id): [parameter.result_type, parameter.unit or "", parameter.ranges or [],
                            parameter.range_text or "", parameter.choices or [],
                            parameter.normal_values or []]
        for parameter in parameters if parameter.is_active
    }
    return json.dumps(entries, sort_keys=True, default=str)


async def mark_order_item_reported_if_done(session: AsyncSession, order_item_id: uuid.UUID) -> None:
    from app.services.investigation_service import mark_order_item_reported

    open_items = (await session.execute(
        select(func.count(LabRequestItem.id)).where(
            LabRequestItem.order_item_id == order_item_id,
            LabRequestItem.status.notin_(["verified", "cancelled"]),
        )
    )).scalar_one()
    if open_items == 0:
        await mark_order_item_reported(session, order_item_id)


class LabService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ================================================================ masters
    async def masters(self, *, kind: Optional[str] = None, include_inactive: bool = False) -> List[LabMaster]:
        statement = select(LabMaster).order_by(LabMaster.kind, LabMaster.position, LabMaster.name)
        if kind:
            statement = statement.where(LabMaster.kind == kind)
        if not include_inactive:
            statement = statement.where(LabMaster.is_active.is_(True))
        return list((await self.session.execute(statement)).scalars())

    async def save_master(self, master_id: Optional[uuid.UUID], data: Dict[str, Any]) -> LabMaster:
        kind = data.get("kind")
        if kind not in rules.MASTER_KINDS:
            raise LabError("Choose which list this belongs to.")
        name = (data.get("name") or "").strip()
        if not name:
            raise LabError("Give the entry a name.")
        clash = select(LabMaster.id).where(LabMaster.kind == kind, func.lower(LabMaster.name) == name.lower())
        if master_id is not None:
            clash = clash.where(LabMaster.id != master_id)
        if (await self.session.execute(clash)).first():
            raise LabError(f"{name} is already on this list.", status_code=409)
        if master_id is None:
            master = LabMaster(kind=kind, name=name)
            self.session.add(master)
        else:
            master = await self.session.get(LabMaster, master_id)
            if master is None:
                raise LabError("That entry no longer exists.", status_code=404)
        master.kind = kind
        master.name = name
        master.code = (data.get("code") or "").strip() or None
        master.category = (data.get("category") or "").strip() or None
        master.position = int(data.get("position") or 0)
        master.is_active = bool(data.get("is_active", True))
        await self.session.flush()
        return master

    async def tests(self, *, q: Optional[str] = None, include_inactive: bool = False) -> List[LabTest]:
        statement = (
            select(LabTest).options(selectinload(LabTest.parameters))
            .order_by(LabTest.group_name, LabTest.position, LabTest.name)
        )
        if q and q.strip():
            like = f"%{q.strip()}%"
            statement = statement.where(or_(LabTest.name.ilike(like), LabTest.code.ilike(like)))
        if not include_inactive:
            statement = statement.where(LabTest.is_active.is_(True))
        return list((await self.session.execute(statement)).scalars())

    async def get_test(self, test_id: uuid.UUID) -> LabTest:
        test = (await self.session.execute(
            select(LabTest).options(selectinload(LabTest.parameters))
            .where(LabTest.id == test_id).execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if test is None:
            raise LabError("That test is not on the test list.", status_code=404)
        return test

    async def save_test(self, test_id: Optional[uuid.UUID], data: Dict[str, Any]) -> LabTest:
        code = (data.get("code") or "").strip().upper()
        name = (data.get("name") or "").strip()
        if not code or not name:
            raise LabError("A test needs a code and a name.")
        clash = select(LabTest.id).where(LabTest.code == code)
        if test_id is not None:
            clash = clash.where(LabTest.id != test_id)
        if (await self.session.execute(clash)).first():
            raise LabError(f"The code {code} is already used by another test.", status_code=409)
        service_code = (data.get("service_code") or "").strip() or None
        if service_code and not (await self.session.execute(
            select(ServiceItem.id).where(ServiceItem.code == service_code)
        )).first():
            raise LabError(f"There is no price-list item with the code {service_code}.")

        is_culture = bool(data.get("is_culture"))
        problems: List[str] = []
        cleaned: List[Dict[str, Any]] = []
        for position, raw in enumerate(data.get("parameters") or []):
            kind = raw.get("result_type") or "numeric"
            line = (raw.get("name") or "").strip()
            label = line or f"Line {position + 1}"
            if kind not in rules.RESULT_TYPES:
                problems.append(f"{label}: unknown result type")
                continue
            if not line:
                problems.append(f"Line {position + 1}: give it a name")
            choices = [str(entry).strip() for entry in raw.get("choices") or [] if str(entry).strip()]
            normal = [str(entry).strip() for entry in raw.get("normal_values") or [] if str(entry).strip()]
            ranges = [rules.clean_range(entry) for entry in raw.get("ranges") or []]
            if kind == "choice":
                if len(choices) < 2:
                    problems.append(f"{label}: give at least two choices")
                known = {entry.lower() for entry in choices}
                if any(entry.lower() not in known for entry in normal):
                    problems.append(f"{label}: every normal value must be one of the choices")
                ranges = []
            elif kind == "numeric":
                problems += [f"{label}: {problem}" for problem in rules.validate_ranges(ranges)]
                choices, normal = [], []
            else:
                choices, normal, ranges = [], [], []
            cleaned.append({
                "id": str(raw["id"]) if raw.get("id") else None,
                "position": position,
                "name": line,
                "analyte_key": (raw.get("analyte_key") or "").strip() or None,
                "aliases": [str(alias).strip() for alias in raw.get("aliases") or [] if str(alias).strip()],
                "result_type": kind,
                "unit": (raw.get("unit") or "").strip() or None,
                "method": (raw.get("method") or "").strip() or None,
                "choices": choices,
                "normal_values": normal,
                "ranges": ranges,
                "range_text": (raw.get("range_text") or "").strip() or None,
                "print_default": bool(raw.get("print_default", True)),
                "is_active": bool(raw.get("is_active", True)),
            })
        if not is_culture and not any(entry["result_type"] != "heading" and entry["is_active"] for entry in cleaned):
            problems.append("Add at least one result line")
        if problems:
            raise LabError("; ".join(problems), status_code=422)

        if test_id is None:
            test = LabTest(code=code, name=name)
            test.parameters = []
            self.session.add(test)
            before = None
        else:
            test = await self.get_test(test_id)
            before = _clinical_signature(test.parameters)

        test.code = code
        test.name = name
        test.group_name = (data.get("group_name") or "").strip() or "General"
        test.specimen = (data.get("specimen") or "").strip() or None
        test.service_code = service_code
        test.catalog_code = (data.get("catalog_code") or "").strip() or None
        test.is_culture = is_culture
        test.turnaround_hours = max(1, int(data.get("turnaround_hours") or 24))
        test.interpretation = (data.get("interpretation") or "").strip() or None
        test.position = int(data.get("position") or 0)
        test.is_active = bool(data.get("is_active", True))
        test.notes = (data.get("notes") or "").strip() or None

        existing = {str(parameter.id): parameter for parameter in test.parameters}
        kept = set()
        for entry in cleaned:
            parameter = existing.get(entry["id"]) if entry["id"] else None
            if parameter is None:
                parameter = LabParameter()
                test.parameters.append(parameter)
            else:
                kept.add(entry["id"])
            for field in _PARAMETER_FIELDS:
                setattr(parameter, field, entry[field])
        # A line removed from the test is retired, not deleted: results
        # already entered against it still name it.
        for key, parameter in existing.items():
            if key not in kept:
                parameter.is_active = False
        await self.session.flush()

        if before is None or before != _clinical_signature(test.parameters):
            test.ranges_reviewed_at = None
            test.ranges_reviewed_by_name = None
        await self.session.flush()
        return await self.get_test(test.id)

    async def review_ranges(self, test_id: uuid.UUID, *, user: User) -> LabTest:
        test = await self.get_test(test_id)
        problems = []
        for parameter in test.parameters:
            if parameter.is_active and parameter.result_type == "numeric":
                problems += [f"{parameter.name}: {problem}" for problem in rules.validate_ranges(parameter.ranges or [])]
        if problems:
            raise LabError("; ".join(problems), status_code=422)
        test.ranges_reviewed_at = _now()
        test.ranges_reviewed_by_name = user.full_name
        await self.session.flush()
        return test

    # ============================================================== numbering
    async def _next_lab_number(self) -> str:
        """LAB26-00001: sequential per year, from the shared document counter."""
        period = f"{local_today().year}"
        lookup = (
            select(DocumentCounter)
            .where(DocumentCounter.scope == "lab", DocumentCounter.period == period)
            .with_for_update()
        )
        counter = (await self.session.execute(lookup)).scalar_one_or_none()
        if counter is None:
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope="lab", period=period, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = (await self.session.execute(lookup)).scalar_one()
        counter.last_value += 1
        await self.session.flush()
        return f"LAB{local_today().year % 100:02d}-{counter.last_value:05d}"

    # =========================================================== registration
    async def get_request(self, request_id: uuid.UUID, *, lock: bool = False) -> LabRequest:
        statement = (
            select(LabRequest).options(selectinload(LabRequest.items))
            .where(LabRequest.id == request_id).execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update(of=LabRequest)
        request = (await self.session.execute(statement)).scalar_one_or_none()
        if request is None:
            raise LabError("That lab request no longer exists.", status_code=404)
        return request

    async def _check_billing(
        self, *, billing: str, patient: Patient, admission: Optional[Admission],
        tests: List[LabTest], user: User,
    ) -> None:
        if billing not in rules.BILLING_MODES:
            raise LabError("Choose how these tests are billed.")
        if billing == "ipd":
            if admission is None:
                raise LabError("Choose the admission these tests are billed to.")
            if admission.status in (AdmissionStatus.DISCHARGED, AdmissionStatus.CANCELLED):
                raise LabError("This admission is closed. Bill the tests at the counter instead.")
            if admission.final_invoice_id is not None:
                raise LabError("The final bill for this admission has been raised. "
                               "Bill these tests at the counter instead.")
        if billing == "invoice" and not has_permission(user.role, Permission.INVOICE_CREATE):
            raise LabError("Raising a bill needs counter rights. Bill the tests to the patient's "
                           "admission, or register them unbilled for the counter.", status_code=403)
        if billing in ("invoice", "ipd"):
            unpriced = [test.name for test in tests if not test.service_code]
            if unpriced:
                raise LabError("No price code is set for " + ", ".join(unpriced)
                               + ". Set one in the lab test list, or register the tests unbilled.")

    async def _bill(self, request: LabRequest, items: List[LabRequestItem], *, user: User) -> None:
        from app.services.ipd_service import IPDError, IPDService
        from app.services.reception_service import ReceptionError, ReceptionService

        tests = {test.id: test for test in (await self.session.execute(
            select(LabTest).where(LabTest.id.in_([item.test_id for item in items]))
        )).scalars()}
        if request.billing == "invoice":
            try:
                invoice = await ReceptionService(self.session).create_invoice(
                    visit_id=None,
                    patient_id=request.patient_id,
                    items=[{"code": tests[item.test_id].service_code, "description": item.name} for item in items],
                    consultant_id=request.consultant_id,
                    doctor_name=request.referred_by,
                    created_by_name=user.full_name,
                )
            except ReceptionError as exc:
                raise LabError(str(exc)) from exc
            request.invoice_id = invoice.id
            lines = list((await self.session.execute(
                select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id).order_by(InvoiceLine.position)
            )).scalars())
            for item, line in zip(items, lines):
                item.unit_rate_paise = line.unit_rate_paise
        elif request.billing == "ipd":
            ipd = IPDService(self.session)
            for item in items:
                try:
                    charge = await ipd.post_charge(
                        admission_id=request.admission_id,
                        category=ChargeCategory.INVESTIGATION,
                        description=f"{item.name} ({request.lab_number})"[:255],
                        service_code=tests[item.test_id].service_code,
                        source_reference=f"lab:{item.id.hex[:24]}",
                        posted_by_name=user.full_name,
                    )
                except IPDError as exc:
                    raise LabError(str(exc)) from exc
                item.charge_id = charge.id
                item.unit_rate_paise = charge.unit_rate_paise
        await self.session.flush()

    async def register(
        self, *, patient_id: uuid.UUID, tests: List[Dict[str, Any]], billing: str,
        admission_id: Optional[uuid.UUID], consultation_id: Optional[uuid.UUID],
        order_id: Optional[uuid.UUID], referred_by: Optional[str], consultant_id: Optional[uuid.UUID],
        priority: str, clinical_notes: Optional[str], user: User,
    ) -> LabRequest:
        if priority not in rules.PRIORITIES:
            raise LabError("Choose routine, urgent or STAT.")
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise LabError("Patient not found.", status_code=404)
        if not tests:
            raise LabError("Choose at least one test.")
        test_ids = [uuid.UUID(str(entry["test_id"])) for entry in tests]
        if len(set(test_ids)) != len(test_ids):
            raise LabError("A test is listed twice.")
        found = {test.id: test for test in (await self.session.execute(
            select(LabTest).where(LabTest.id.in_(test_ids))
        )).scalars()}
        unavailable = [str(test_id) for test_id in test_ids if test_id not in found or not found[test_id].is_active]
        if unavailable:
            raise LabError("One of the chosen tests is no longer offered.")
        ordered_tests = [found[test_id] for test_id in test_ids]

        admission = None
        if admission_id is not None:
            admission = await self.session.get(Admission, admission_id)
            if admission is None or admission.patient_id != patient.id:
                raise LabError("That admission is not this patient's.")
        await self._check_billing(billing=billing, patient=patient, admission=admission,
                                  tests=ordered_tests, user=user)

        order_items = [uuid.UUID(str(entry["order_item_id"])) for entry in tests if entry.get("order_item_id")]
        if order_items:
            rows = (await self.session.execute(
                select(InvestigationOrderItem, InvestigationOrder)
                .join(InvestigationOrder, InvestigationOrder.id == InvestigationOrderItem.order_id)
                .where(InvestigationOrderItem.id.in_(order_items))
            )).all()
            if len(rows) != len(set(order_items)):
                raise LabError("One of the doctor's orders could not be found.")
            for item, order in rows:
                if order.patient_id != patient.id:
                    raise LabError("That order is for a different patient.")
                if order.status == OrderStatus.CANCELLED:
                    raise LabError(f"The order for {item.name} was cancelled by the doctor.")
                order_id = order_id or order.id
            already = (await self.session.execute(
                select(LabRequestItem.name).where(
                    LabRequestItem.order_item_id.in_(order_items), LabRequestItem.status != "cancelled")
            )).scalars().all()
            if already:
                raise LabError(f"{', '.join(already)} is already registered from this order.", status_code=409)

        if consultant_id is not None and not (referred_by or "").strip():
            consultant = await self.session.get(Consultant, consultant_id)
            referred_by = consultant.full_name if consultant else None

        request = LabRequest(
            lab_number=await self._next_lab_number(),
            patient_id=patient.id,
            admission_id=admission.id if admission else None,
            consultation_id=consultation_id,
            order_id=order_id,
            billing=billing,
            status="registered",
            priority=priority,
            referred_by=(referred_by or "").strip() or None,
            consultant_id=consultant_id,
            clinical_notes=(clinical_notes or "").strip() or None,
            registered_by_id=user.id,
            registered_by_name=user.full_name,
        )
        self.session.add(request)
        await self.session.flush()

        items = []
        for position, entry in enumerate(tests):
            test = ordered_tests[position]
            item = LabRequestItem(
                request_id=request.id, test_id=test.id,
                order_item_id=uuid.UUID(str(entry["order_item_id"])) if entry.get("order_item_id") else None,
                position=position, code=test.code, name=test.name, group_name=test.group_name,
                specimen=test.specimen, is_culture=test.is_culture, status="registered",
                results=[], amendments=[],
            )
            self.session.add(item)
            items.append(item)
        await self.session.flush()
        await self._bill(request, items, user=user)
        logger.info("lab_registered", extra={"lab_number": request.lab_number, "tests": len(items),
                                              "billing": billing})
        return await self.get_request(request.id)

    async def bill_later(
        self, request_id: uuid.UUID, *, billing: str, admission_id: Optional[uuid.UUID], user: User
    ) -> LabRequest:
        request = await self.get_request(request_id, lock=True)
        if request.status == "cancelled":
            raise LabError("This request is cancelled.")
        if request.billing != "unbilled":
            raise LabError("These tests are already billed.", status_code=409)
        if billing == "unbilled":
            raise LabError("Choose a bill or the admission.")
        patient = await self.session.get(Patient, request.patient_id)
        admission = None
        target = admission_id or request.admission_id
        if target is not None:
            admission = await self.session.get(Admission, target)
            if admission is None or admission.patient_id != patient.id:
                raise LabError("That admission is not this patient's.")
        live = [item for item in request.items if item.status != "cancelled"]
        tests = list((await self.session.execute(
            select(LabTest).where(LabTest.id.in_([item.test_id for item in live]))
        )).scalars())
        if len(tests) != len(live):
            raise LabError("A test on this request has been removed from the test list; bill it at the counter by hand.")
        await self._check_billing(billing=billing, patient=patient, admission=admission, tests=tests, user=user)
        request.billing = billing
        if billing == "ipd":
            request.admission_id = admission.id
        await self._bill(request, live, user=user)
        return await self.get_request(request.id)

    async def collect(self, request_id: uuid.UUID, *, user: User) -> LabRequest:
        request = await self.get_request(request_id, lock=True)
        if request.status == "cancelled":
            raise LabError("This request is cancelled.")
        if request.sample_collected_at is not None:
            raise LabError("The sample is already marked collected.", status_code=409)
        request.sample_collected_at = _now()
        request.sample_collected_by_name = user.full_name
        for item in request.items:
            if item.status == "registered":
                item.status = "collected"
        request.status = rules.request_status(item.status for item in request.items)
        await self.session.flush()
        return request

    # ================================================================ lists
    async def list_requests(
        self, *, q: Optional[str] = None, status: Optional[str] = None, date_from=None, date_to=None,
        patient_id: Optional[uuid.UUID] = None, admission_id: Optional[uuid.UUID] = None, limit: int = 100,
    ) -> List[tuple]:
        statement = (
            select(LabRequest, Patient)
            .join(Patient, Patient.id == LabRequest.patient_id)
            .options(selectinload(LabRequest.items))
            .order_by(LabRequest.created_at.desc())
            .limit(limit)
        )
        if status == "pending":
            statement = statement.where(LabRequest.status.notin_(["verified", "cancelled"]))
        elif status:
            statement = statement.where(LabRequest.status == status)
        if date_from is not None:
            statement = statement.where(LabRequest.created_at >= day_bounds(date_from)[0])
        if date_to is not None:
            statement = statement.where(LabRequest.created_at < day_bounds(date_to)[1])
        if patient_id is not None:
            statement = statement.where(LabRequest.patient_id == patient_id)
        if admission_id is not None:
            statement = statement.where(LabRequest.admission_id == admission_id)
        if q and q.strip():
            like = f"%{q.strip()}%"
            statement = statement.where(or_(
                LabRequest.lab_number.ilike(like), Patient.name.ilike(like),
                Patient.uhid.ilike(like), Patient.phone_number.ilike(like),
            ))
        return list((await self.session.execute(statement)).all())

    async def pending_orders(self, *, limit: int = 300) -> List[Dict[str, Any]]:
        """Tests doctors have ordered that the laboratory has not registered yet."""
        tests_by_code = {
            test.catalog_code: test for test in (await self.session.execute(
                select(LabTest).where(LabTest.is_active.is_(True), LabTest.catalog_code.isnot(None))
            )).scalars()
        }
        registered = select(LabRequestItem.order_item_id).where(
            LabRequestItem.order_item_id.isnot(None), LabRequestItem.status != "cancelled")
        rows = (await self.session.execute(
            select(InvestigationOrderItem, InvestigationOrder, Patient)
            .join(InvestigationOrder, InvestigationOrder.id == InvestigationOrderItem.order_id)
            .join(Patient, Patient.id == InvestigationOrder.patient_id)
            .where(
                InvestigationOrderItem.reported.is_(False),
                InvestigationOrder.status.notin_([OrderStatus.DRAFT, OrderStatus.CANCELLED]),
                InvestigationOrderItem.id.notin_(registered),
            )
            .order_by(InvestigationOrder.created_at)
            .limit(limit)
        )).all()
        patient_ids = {patient.id for _item, _order, patient in rows}
        admissions = {}
        if patient_ids:
            for admission in (await self.session.execute(
                select(Admission).where(
                    Admission.patient_id.in_(patient_ids),
                    Admission.status.notin_([AdmissionStatus.DISCHARGED, AdmissionStatus.CANCELLED]),
                )
            )).scalars():
                admissions[admission.patient_id] = admission

        grouped: Dict[uuid.UUID, Dict[str, Any]] = {}
        for item, order, patient in rows:
            category = item.category.value
            test = tests_by_code.get(item.code)
            if category not in LAB_CATEGORIES and not (category in MIXED_CATEGORIES and test is not None):
                continue
            entry = grouped.get(order.id)
            if entry is None:
                admission = admissions.get(patient.id)
                entry = grouped[order.id] = {
                    "order_id": order.id,
                    "consultation_id": order.consultation_id,
                    "ordered_at": order.issued_at or order.created_at,
                    "ordered_by_name": order.ordered_by_name,
                    "priority": order.priority.value,
                    "clinical_notes": order.clinical_notes,
                    "provisional_diagnosis": order.provisional_diagnosis,
                    "patient": {"id": patient.id, "name": patient.name, "uhid": patient.uhid,
                                "age": patient.age, "gender": patient.gender.value},
                    "admission": {"id": admission.id, "ip_number": admission.ip_number} if admission else None,
                    "items": [],
                }
            entry["items"].append({
                "item_id": item.id, "code": item.code, "name": item.name, "category": category,
                "test": {"id": test.id, "code": test.code, "name": test.name,
                         "priced": bool(test.service_code)} if test else None,
            })
        return list(grouped.values())

    async def patient_results(
        self, patient_id: uuid.UUID, *, admission_id: Optional[uuid.UUID] = None, limit: int = 200
    ) -> List[tuple]:
        statement = (
            select(LabRequestItem, LabRequest)
            .join(LabRequest, LabRequest.id == LabRequestItem.request_id)
            .where(LabRequest.patient_id == patient_id, LabRequestItem.status == "verified")
            .order_by(LabRequestItem.verified_at.desc())
            .limit(limit)
        )
        if admission_id is not None:
            statement = statement.where(LabRequest.admission_id == admission_id)
        return list((await self.session.execute(statement)).all())

    # ================================================================ results
    async def active_parameters(self, test_id: uuid.UUID) -> List[Dict[str, Any]]:
        rows = (await self.session.execute(
            select(LabParameter)
            .where(LabParameter.test_id == test_id, LabParameter.is_active.is_(True))
            .order_by(LabParameter.position)
        )).scalars()
        return [parameter_dict(parameter) for parameter in rows]

    async def _item_context(self, item_id: uuid.UUID, *, lock: bool = False):
        statement = select(LabRequestItem).where(LabRequestItem.id == item_id)
        if lock:
            statement = statement.with_for_update()
        item = (await self.session.execute(statement)).scalar_one_or_none()
        if item is None:
            raise LabError("That test is no longer on the request.", status_code=404)
        request = await self.session.get(LabRequest, item.request_id)
        patient = await self.session.get(Patient, request.patient_id)
        test = await self.session.get(LabTest, item.test_id) if item.test_id else None
        return item, request, patient, test

    async def _refresh_status(self, request: LabRequest) -> None:
        await self.session.flush()
        states = (await self.session.execute(
            select(LabRequestItem.status).where(LabRequestItem.request_id == request.id)
        )).scalars().all()
        request.status = rules.request_status(states)

    async def save_results(
        self, item_id: uuid.UUID, *, values: Dict[str, Optional[str]], prints: Dict[str, bool],
        remarks: Optional[str], culture: Optional[Dict[str, Any]], user: User,
    ) -> LabRequestItem:
        item, request, patient, test = await self._item_context(item_id, lock=True)
        if item.status == "cancelled" or request.status == "cancelled":
            raise LabError("This test is cancelled.")
        if item.status == "verified":
            raise LabError("This result is verified. Reopen it with a reason to correct it.", status_code=409)
        if request.sample_collected_at is None:
            raise LabError("Mark the sample collected before entering results.")
        if test is None:
            raise LabError("This test has been removed from the test list.")

        if item.is_culture:
            item.culture = rules.clean_culture(culture)
            has_any = item.culture["growth"] is not None
        else:
            parameters = await self.active_parameters(test.id)
            rows, errors = rules.evaluate_all(
                parameters,
                {str(key): value for key, value in (values or {}).items()},
                {str(key): bool(value) for key, value in (prints or {}).items()},
                sex=patient_sex(patient), age=patient.age,
            )
            if errors:
                raise LabError("; ".join(errors), status_code=422)
            item.results = rows
            has_any = any(row["value"] for row in rows)
        item.remarks = (remarks or "").strip() or None
        if has_any:
            item.status = "entered"
            item.entered_at = _now()
            item.entered_by_name = user.full_name
        else:
            item.status = "collected"
        await self._refresh_status(request)
        await self.session.flush()
        return item

    async def verify(self, item_id: uuid.UUID, *, critical_note: Optional[str], user: User) -> LabRequestItem:
        item, request, patient, test = await self._item_context(item_id, lock=True)
        if item.status == "verified":
            raise LabError("This result is already verified.", status_code=409)
        if item.status != "entered":
            raise LabError("Enter the results before verifying them.")
        if test is None:
            raise LabError("This test has been removed from the test list.")
        if not item.is_culture and test.ranges_reviewed_at is None:
            raise LabError(
                f"The reference ranges for {test.name} have not been reviewed. A doctor must review "
                "them in the lab test list before this result can be verified.", status_code=409)

        rows: List[Dict[str, Any]] = []
        errors: List[str] = []
        if not item.is_culture:
            parameters = await self.active_parameters(test.id)
            stored = item.results or []
            rows, errors = rules.evaluate_all(
                parameters,
                {row["parameter_id"]: row.get("value") for row in stored},
                {row["parameter_id"]: bool(row.get("print", True)) for row in stored},
                sex=patient_sex(patient), age=patient.age,
            )
        problems = rules.check_for_verify(is_culture=item.is_culture, rows=rows, culture=item.culture,
                                          errors=errors)
        if problems:
            raise LabError("; ".join(problems), status_code=422)
        critical = rules.critical_rows(rows)
        note = (critical_note or "").strip()
        if critical and len(note) < 5:
            listed = ", ".join(f"{row['name']} {row['value']}" for row in critical)
            raise LabError(f"Critical result: {listed}. Record who was told, and when, before verifying.",
                           status_code=422)

        consultant = (await self.session.execute(
            select(Consultant).where(Consultant.user_id == user.id)
        )).scalars().first()
        if not item.is_culture:
            item.results = rows
        item.critical_note = note or None
        item.status = "verified"
        item.verified_at = _now()
        item.verified_by_id = user.id
        item.verified_by_name = user.full_name
        item.verifier_qualification = consultant.qualification if consultant else None
        item.verifier_registration = consultant.registration_number if consultant else None
        await self._refresh_status(request)
        if item.order_item_id is not None:
            await mark_order_item_reported_if_done(self.session, item.order_item_id)
        await self.session.flush()
        return item

    async def reopen(self, item_id: uuid.UUID, *, reason: str, user: User) -> LabRequestItem:
        item, request, _patient, _test = await self._item_context(item_id, lock=True)
        if item.status != "verified":
            raise LabError("Only a verified result can be reopened.")
        reason = (reason or "").strip()
        if len(reason) < 5:
            raise LabError("Say why the verified result is being corrected.")
        history = list(item.amendments or [])
        history.append({
            "version": item.version,
            "verified_at": item.verified_at.isoformat() if item.verified_at else None,
            "verified_by_name": item.verified_by_name,
            "results": item.results,
            "culture": item.culture,
            "remarks": item.remarks,
            "critical_note": item.critical_note,
            "reason": reason,
            "reopened_at": _now().isoformat(),
            "reopened_by_name": user.full_name,
        })
        item.amendments = history
        item.version += 1
        item.status = "entered"
        item.verified_at = None
        item.verified_by_id = None
        item.verified_by_name = None
        item.verifier_qualification = None
        item.verifier_registration = None
        item.critical_note = None
        await self._refresh_status(request)
        await self.session.flush()
        return item

    # ============================================================ cancelling
    async def cancel(
        self, request_id: uuid.UUID, *, item_ids: Optional[List[uuid.UUID]], reason: str, user: User
    ) -> Dict[str, Any]:
        from app.services.reception_service import ReceptionError, ReceptionService

        reason = (reason or "").strip()
        if len(reason) < 5:
            raise LabError("Say why the test is being cancelled.")
        request = await self.get_request(request_id, lock=True)
        targets = [item for item in request.items
                   if item.status != "cancelled" and (item_ids is None or item.id in item_ids)]
        if item_ids is not None and len(targets) != len(set(item_ids)):
            raise LabError("That test is not on this request, or is already cancelled.")
        if not targets:
            raise LabError("There is nothing left to cancel on this request.")
        verified = [item.name for item in targets if item.status == "verified"]
        if verified:
            raise LabError(f"{', '.join(verified)} is verified. A verified result cannot be cancelled.",
                           status_code=409)

        for item in targets:
            if item.charge_id is not None:
                charge = await self.session.get(AdmissionCharge, item.charge_id)
                if charge is not None:
                    if charge.is_billed:
                        raise LabError(f"{item.name} is already on the admission's final bill.", status_code=409)
                    await self.session.delete(charge)
                item.charge_id = None
            item.status = "cancelled"
            item.cancelled_at = _now()
            item.cancel_reason = reason
            item.cancelled_by_name = user.full_name
        await self.session.flush()

        notes: List[str] = []
        refund_due = 0
        if request.billing == "invoice" and request.invoice_id is not None:
            invoice = await self.session.get(Invoice, request.invoice_id)
            remaining = [item for item in request.items if item.status != "cancelled"]
            reception = ReceptionService(self.session)
            if invoice is not None and invoice.status is not InvoiceStatus.CANCELLED:
                try:
                    if invoice.paid_paise != 0:
                        refund_due = sum(item.unit_rate_paise for item in targets)
                        notes.append(
                            f"Bill {invoice.invoice_number} was already paid. Refund Rs {refund_due / 100:,.2f} "
                            "for the cancelled tests at the counter.")
                    elif remaining:
                        tests = {test.id: test for test in (await self.session.execute(
                            select(LabTest).where(LabTest.id.in_([item.test_id for item in remaining if item.test_id]))
                        )).scalars()}
                        await reception.amend_invoice(
                            invoice_id=invoice.id,
                            items=[{"code": tests[item.test_id].service_code if item.test_id in tests else None,
                                    "description": item.name, "unit_rate_paise": item.unit_rate_paise}
                                   for item in remaining],
                            reason=f"Lab test cancelled: {reason}"[:500],
                            amended_by_name=user.full_name,
                        )
                        notes.append(f"Bill {invoice.invoice_number} was corrected to the remaining tests.")
                    else:
                        await reception.cancel_invoice(invoice.id, reason=f"Lab tests cancelled: {reason}"[:500])
                        notes.append(f"Bill {invoice.invoice_number} was cancelled.")
                except ReceptionError as exc:
                    raise LabError(str(exc)) from exc

        await self._refresh_status(request)
        if request.status == "cancelled":
            request.cancelled_at = _now()
            request.cancel_reason = reason
            request.cancelled_by_name = user.full_name
        await self.session.flush()
        return {"refund_due_paise": refund_due, "notes": notes}

    # ============================================================= printout
    async def read_printout(
        self, item_id: uuid.UUID, *, data: bytes, content_type: str, filename: str
    ) -> Dict[str, Any]:
        """Suggested values from an analyser printout. Nothing is saved."""
        from app.investigations.extraction import extract
        from app.investigations.parsing import parse_report_text
        from app.investigations.reference_ranges import _clean, normalize_unit

        item, _request, _patient, test = await self._item_context(item_id)
        if item.is_culture:
            raise LabError("A culture report is entered by hand.")
        if item.status in ("verified", "cancelled"):
            raise LabError("Results can only be read into a test that is still open.")
        if test is None:
            raise LabError("This test has been removed from the test list.")

        unclear = {"unclear": True, "message": PRINTOUT_UNCLEAR, "suggestions": [], "conflicts": [],
                   "unit_mismatches": [], "unmatched_lines": [], "unmatched_count": 0}
        try:
            extracted = await asyncio.to_thread(extract, data, content_type, filename)
        except Exception:  # noqa: BLE001 - an unreadable file is an unclear printout, not a crash
            logger.exception("lab_printout_extract_failed")
            return unclear
        if not extracted.ok or not extracted.legible:
            return unclear
        parameters = await self.active_parameters(test.id)
        matched = rules.match_printout(parameters, parse_report_text(extracted.text),
                                       normalize_unit=normalize_unit, clean_name=_clean)
        if not matched["suggestions"]:
            return {**unclear, **{key: value for key, value in matched.items() if key != "suggestions"}}
        return {"unclear": False, "message": None, **matched}
