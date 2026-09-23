"""The Visit Pad: opening, writing, signing and correcting clinical documents.

Everything a doctor does to a pad goes through here. The rules that make the
record trustworthy live in this file and nowhere else:

* A signed document is never changed. `amend` makes a new draft in the same
  group; signing that draft marks the original superseded.
* Only one draft exists per consultation and document type, enforced by a
  unique index, so two doctors opening the same patient land on one draft.
* Autosave is checked against the version the browser last saw. A save based
  on a stale copy is refused rather than silently overwriting a colleague.
* An AI-drafted section stays marked as AI-drafted after it is edited.

Section rules — what a value may hold, how templates merge, what carries
forward — are in `app/pads/sections.py`, which has no database in it.
"""
import uuid
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_today
from app.core.logging import get_logger
from app.models.consultation import Consultation
from app.models.enums import Department, PadStatus
from app.models.pad import PadCatalogueEntry, PadDocument, PadLayout, PadTemplate
from app.models.patient import Patient
from app.models.user import User
from app.pads import forms
from app.pads import sections as rules
from app.pads.defaults import DOCUMENT_TYPES, PROTECTED_SECTIONS, default_layout
from app.pads.defaults import document_type as type_spec
from app.models.ipd import Admission
from app.models.consultant import Consultant
from app.services.prescription_service import PrescriptionService

logger = get_logger(__name__)


def layout_protection_problems(document_type: str, sections: List[Dict[str, Any]]) -> List[str]:
    """Why a layout would break something the system depends on. Empty when it would not."""
    spec = type_spec(document_type)
    if spec is not None and spec.family:
        return [f"{spec.label} has fixed fields and wording; its layout cannot be changed."]
    problems: List[str] = []
    builtin = {section["key"]: section for section in default_layout(document_type) or []}
    given = {section["key"]: section for section in sections}
    for key, field_keys in PROTECTED_SECTIONS.get(document_type, {}).items():
        original = builtin.get(key)
        if original is None:
            continue
        found = given.get(key)
        if found is None:
            problems.append(f"The section \"{original['title']}\" is used when the document is signed and cannot be removed.")
            continue
        if found.get("kind") != original["kind"]:
            problems.append(f"The section \"{original['title']}\" must stay a {original['kind']} section.")
        fields_now = {field["key"]: field for field in found.get("fields") or []}
        labels = {field["key"]: field["label"] for field in original.get("fields") or []}
        for field_key in field_keys:
            if field_key not in fields_now:
                problems.append(f"\"{labels.get(field_key, field_key)}\" in \"{original['title']}\" cannot be removed.")
            elif not fields_now[field_key].get("required"):
                problems.append(f"\"{labels.get(field_key, field_key)}\" in \"{original['title']}\" must stay required.")
    return problems


class PadError(Exception):
    """A request the pad cannot honour, with a message a doctor can act on."""

    status_code = 400


class PadNotFound(PadError):
    status_code = 404


class PadConflict(PadError):
    status_code = 409


class PadForbidden(PadError):
    status_code = 403


class PadUnavailable(PadError):
    status_code = 503


# Layout scopes, most specific first.
SCOPES = ("personal", "department", "hospital")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _review_date(follow_up: Dict[str, Any]) -> Optional[datetime]:
    """When the patient is to be seen again.

    The pad asks for a number of days, because that is how it is said in the
    room. A date is what the patient's copy needs, so the count is turned into
    one here — from today, the day the pad is signed.

    "Only if needed" is not a date and must not become one: a follow-up nobody
    asked for would appear in the appointment book.
    """
    chosen = str(follow_up.get("after_days") or "").strip()
    match = re.match(r"^(\d{1,3})\s*day", chosen, re.IGNORECASE)
    if match:
        return datetime.combine(
            local_today() + timedelta(days=int(match.group(1))), time.min, tzinfo=timezone.utc
        )
    # Layouts written before the pad asked in days may still hold a date.
    legacy = follow_up.get("date")
    if legacy:
        try:
            return datetime.fromisoformat(str(legacy))
        except ValueError:
            return None
    return None


class PadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ================================================================ layouts
    @staticmethod
    def _require_type(document_type: str) -> None:
        if document_type not in DOCUMENT_TYPES:
            raise PadNotFound(f"There is no document type called {document_type!r}.")

    def _scope_filter(
        self,
        document_type: str,
        scope: str,
        department: Optional[Department],
        user_id: Optional[uuid.UUID],
    ):
        conditions = [PadLayout.document_type == document_type]
        if scope == "personal":
            conditions += [PadLayout.owner_id == user_id]
            conditions += [
                PadLayout.department == department if department else PadLayout.department.is_(None)
            ]
        elif scope == "department":
            conditions += [PadLayout.owner_id.is_(None), PadLayout.department == department]
        else:
            conditions += [PadLayout.owner_id.is_(None), PadLayout.department.is_(None)]
        return and_(*conditions)

    async def resolve_layout(
        self,
        document_type: str,
        *,
        department: Optional[Department],
        user_id: Optional[uuid.UUID],
    ) -> Tuple[Optional[PadLayout], List[Dict[str, Any]], str]:
        """The layout a user sees. Returns (row or None, sections, scope)."""
        self._require_type(document_type)
        for scope in SCOPES:
            if scope == "personal" and user_id is None:
                continue
            if scope == "department" and department is None:
                continue
            row = (
                await self.session.execute(
                    select(PadLayout).where(
                        self._scope_filter(document_type, scope, department, user_id)
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                return row, row.sections, scope
        # Built-in layouts are written as only what differs from the defaults.
        # They go through the same validation as a saved layout so every
        # switch is filled in: without it, a section with no `visible_in_pad`
        # reached the browser as undefined and the pad rendered nothing.
        builtin = default_layout(document_type)
        return None, rules.validate_layout(builtin) if builtin else [], "default"

    async def save_layout(
        self,
        document_type: str,
        *,
        scope: str,
        name: str,
        sections: List[Dict[str, Any]],
        department: Optional[Department],
        user: User,
    ) -> PadLayout:
        self._require_type(document_type)
        if scope not in SCOPES:
            raise PadError(f"Unknown layout scope {scope!r}.")
        if scope == "department" and department is None:
            raise PadError("A department layout needs a department.")
        try:
            validated = rules.validate_layout(sections)
        except rules.LayoutError as exc:
            raise PadError(str(exc)) from exc
        problems = layout_protection_problems(document_type, validated)
        if problems:
            raise PadError(" ".join(problems))

        row = (
            await self.session.execute(
                select(PadLayout).where(
                    self._scope_filter(document_type, scope, department, user.id)
                ).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            row = PadLayout(
                document_type=document_type,
                department=department if scope != "hospital" else None,
                owner_id=user.id if scope == "personal" else None,
                name=name.strip() or DOCUMENT_TYPES[document_type],
                sections=validated,
                revision=1,
                updated_by_name=user.full_name,
            )
            self.session.add(row)
        else:
            row.name = name.strip() or row.name
            row.sections = validated
            row.revision += 1
            row.updated_by_name = user.full_name
        await self.session.commit()
        logger.info(
            "pad_layout_saved",
            extra={"document_type": document_type, "scope": scope, "by": user.full_name},
        )
        return row

    async def reset_layout(
        self,
        document_type: str,
        *,
        scope: str,
        department: Optional[Department],
        user: User,
    ) -> bool:
        """Remove a scope's layout so the next one out applies again."""
        self._require_type(document_type)
        result = await self.session.execute(
            delete(PadLayout).where(
                self._scope_filter(document_type, scope, department, user.id)
            )
        )
        await self.session.commit()
        return bool(result.rowcount)

    # ============================================================== documents
    async def get(self, document_id: uuid.UUID) -> PadDocument:
        document = await self.session.get(PadDocument, document_id)
        if document is None:
            raise PadNotFound("That document no longer exists.")
        return document

    async def _draft_for(
        self, consultation_id: uuid.UUID, document_type: str
    ) -> Optional[PadDocument]:
        return (
            await self.session.execute(
                select(PadDocument).where(
                    PadDocument.consultation_id == consultation_id,
                    PadDocument.document_type == document_type,
                    PadDocument.status == PadStatus.DRAFT,
                )
            )
        ).scalar_one_or_none()

    async def _latest_signed_for(
        self, consultation_id: uuid.UUID, document_type: str
    ) -> Optional[PadDocument]:
        return (
            await self.session.execute(
                select(PadDocument)
                .where(
                    PadDocument.consultation_id == consultation_id,
                    PadDocument.document_type == document_type,
                    PadDocument.status == PadStatus.SIGNED,
                )
                .order_by(PadDocument.signed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def open_for_consultation(
        self, consultation_id: uuid.UUID, document_type: str, *, user: User
    ) -> PadDocument:
        """The document a doctor should be looking at for this consultation.

        A draft in progress if there is one; otherwise the signed document,
        which can be amended; otherwise a new draft, with its AI sections
        already drafted from the intake so the doctor edits rather than types.
        """
        self._require_type(document_type)
        if type_spec(document_type).scope != "consultation":
            raise PadError(f"{DOCUMENT_TYPES[document_type]} belongs to an admission, not an OPD visit.")
        consultation = await self.session.get(Consultation, consultation_id)
        if consultation is None:
            raise PadNotFound("Consultation not found.")

        existing = await self._draft_for(consultation_id, document_type)
        if existing is not None:
            # Vitals saved at intake after this draft was made are brought in
            # when the pad is opened — never while it is open, which would
            # collide with the doctor's autosave — and only where the doctor
            # has not typed their own readings.
            values, provenance, changed = rules.refresh_intake_vitals(
                existing.sections, existing.values, existing.provenance,
                (consultation.medical_json or {}).get("vitals"),
            )
            if changed:
                existing.values = values
                existing.provenance = provenance
                await self.session.commit()
                await self.session.refresh(existing)
            return existing
        signed = await self._latest_signed_for(consultation_id, document_type)
        if signed is not None:
            return signed

        layout, sections, _scope = await self.resolve_layout(
            document_type, department=consultation.department, user_id=user.id
        )
        values, provenance = rules.draft_from_intake(sections, consultation.medical_json)

        document = PadDocument(
            document_type=document_type,
            title=DOCUMENT_TYPES[document_type],
            patient_id=consultation.patient_id,
            consultation_id=consultation.id,
            department=consultation.department,
            layout_id=layout.id if layout else None,
            layout_revision=layout.revision if layout else 0,
            sections=sections,
            values=values,
            provenance=provenance,
            status=PadStatus.DRAFT,
            author_id=user.id,
            author_name=user.full_name,
            group_id=uuid.uuid4(),
            version=1,
        )
        self.session.add(document)
        try:
            await self.session.commit()
        except IntegrityError:
            # Someone else opened this patient's pad in the same instant. The
            # unique draft index refused the second draft; use the first.
            await self.session.rollback()
            existing = await self._draft_for(consultation_id, document_type)
            if existing is None:
                raise
            return existing
        logger.info(
            "pad_opened",
            extra={
                "document_id": str(document.id),
                "consultation_id": str(consultation_id),
                "ai_sections": len(provenance),
            },
        )
        return document

    async def open_for_admission(
        self,
        admission_id: uuid.UUID,
        document_type: str,
        *,
        user: User,
        new: bool = False,
    ) -> PadDocument:
        """The document someone should be looking at for this admission.

        One-per-admission documents (admission note, nursing assessment,
        discharge summary) behave like the OPD pad: the draft in progress, else
        the signed copy, else a new draft.

        Many-per-admission documents (progress notes, nursing notes) return the
        caller's own unfinished note if they left one — an interrupted ward
        round is resumed, not duplicated — and otherwise, or whenever `new` is
        asked for, start a fresh one.
        """
        spec = type_spec(document_type)
        if spec is None:
            raise PadNotFound(f"There is no document type called {document_type!r}.")
        if spec.scope != "admission":
            raise PadError(f"{spec.label} belongs to an OPD visit, not an admission.")

        # The admission row is locked so two people opening the same
        # one-per-admission document at once land on one draft. The OPD pad
        # has a unique index for this; here "one" and "many" share a table and
        # an index cannot tell them apart.
        admission = (
            await self.session.execute(
                select(Admission).where(Admission.id == admission_id).with_for_update()
            )
        ).scalar_one_or_none()
        if admission is None:
            raise PadNotFound("Admission not found.")

        existing = select(PadDocument).where(
            PadDocument.admission_id == admission_id,
            PadDocument.document_type == document_type,
        )
        found: Optional[PadDocument] = None
        if spec.many:
            if not new:
                found = (
                    await self.session.execute(
                        existing.where(
                            PadDocument.status == PadStatus.DRAFT,
                            PadDocument.author_id == user.id,
                        ).order_by(PadDocument.created_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()
        else:
            found = (
                await self.session.execute(
                    existing.where(PadDocument.status == PadStatus.DRAFT).limit(1)
                )
            ).scalar_one_or_none()
            if found is None:
                found = (
                    await self.session.execute(
                        existing.where(PadDocument.status == PadStatus.SIGNED)
                        .order_by(PadDocument.signed_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
        if found is not None:
            await self.session.commit()  # release the lock
            return found

        if admission.status.value not in ("admitted", "discharge_initiated"):
            await self.session.rollback()
            raise PadConflict(
                "This patient has been discharged. Their documents can still be "
                "corrected, but new ones cannot be started."
            )

        layout, sections, _scope = await self.resolve_layout(
            document_type, department=admission.department, user_id=user.id
        )
        # Copied from the admission once, when the draft is made. A final
        # diagnosis is only copied if one was recorded; the provisional
        # diagnosis is not quietly promoted into the final one.
        values, provenance = rules.draft_from_record(
            sections,
            {
                "reason_for_admission": admission.reason_for_admission,
                "provisional_diagnosis": admission.provisional_diagnosis,
                "final_diagnosis": admission.final_diagnosis,
                "allergies": admission.allergies or [],
            },
        )

        document = PadDocument(
            document_type=document_type,
            title=spec.label,
            patient_id=admission.patient_id,
            admission_id=admission.id,
            department=admission.department,
            layout_id=layout.id if layout else None,
            layout_revision=layout.revision if layout else 0,
            sections=sections,
            values=values,
            provenance=provenance,
            status=PadStatus.DRAFT,
            author_id=user.id,
            author_name=user.full_name,
            group_id=uuid.uuid4(),
            version=1,
        )
        self.session.add(document)
        await self.session.commit()
        logger.info(
            "pad_opened_for_admission",
            extra={"document_id": str(document.id), "admission": admission.ip_number,
                   "type": document_type, "by": user.full_name},
        )
        return document

    async def open_for_patient(
        self,
        patient_id: uuid.UUID,
        document_type: str,
        *,
        user: User,
        consultation_id: Optional[uuid.UUID] = None,
        admission_id: Optional[uuid.UUID] = None,
        surgery_id: Optional[uuid.UUID] = None,
        order_item_id: Optional[uuid.UUID] = None,
        new: bool = False,
    ) -> PadDocument:
        """A certificate, consent form or radiology report for a patient.

        The caller's own unfinished form of this kind, for the same visit,
        admission or surgery, is resumed rather than duplicated; otherwise, or
        when `new` is asked for, a fresh one is started from what the hospital
        already knows.
        """
        from app.core.clock import to_local
        from app.models.theatre import Surgery

        spec = type_spec(document_type)
        if spec is None:
            raise PadNotFound(f"There is no document type called {document_type!r}.")
        if spec.scope != "patient":
            raise PadError(f"{spec.label} is not a certificate or consent form.")
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise PadNotFound("Patient not found.")

        consultation = await self.session.get(Consultation, consultation_id) if consultation_id else None
        surgery = await self.session.get(Surgery, surgery_id) if surgery_id else None
        if surgery is not None and admission_id is None:
            admission_id = surgery.admission_id
        admission = await self.session.get(Admission, admission_id) if admission_id else None
        for linked, label in ((consultation, "visit"), (admission, "admission"), (surgery, "surgery")):
            if linked is not None and linked.patient_id != patient.id:
                raise PadError(f"That {label} belongs to another patient.")
        if consultation_id and consultation is None:
            raise PadNotFound("Consultation not found.")
        if admission_id and admission is None:
            raise PadNotFound("Admission not found.")
        if surgery_id and surgery is None:
            raise PadNotFound("Surgery not found.")
        order_item = order = None
        if order_item_id is not None:
            from app.models.investigation import InvestigationOrder, InvestigationOrderItem

            if document_type != "radiology_report":
                raise PadError("Only a radiology report is written against an order.")
            order_item = await self.session.get(InvestigationOrderItem, order_item_id)
            order = await self.session.get(InvestigationOrder, order_item.order_id) if order_item else None
            if order_item is None or order is None:
                raise PadNotFound("That investigation order was not found.")
            if order.patient_id != patient.id:
                raise PadError("That investigation was ordered for another patient.")
            if order_item.category.value not in forms.IMAGING_CATEGORIES:
                raise PadError(f"{order_item.name} is not an imaging study.")
            if order.status.value == "cancelled":
                raise PadConflict("That order was cancelled.")
            if consultation is None and order.consultation_id:
                consultation = await self.session.get(Consultation, order.consultation_id)
            if not new:
                reported = (
                    await self.session.execute(
                        select(PadDocument).where(
                            PadDocument.order_item_id == order_item.id,
                            PadDocument.status == PadStatus.SIGNED,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if reported is not None:
                    return reported

        if spec.requires == "admission" and admission is None:
            raise PadError(f"{spec.label} is written for an admission. Open it from the case sheet.")
        if document_type == "lama_form" and admission.status.value not in ("admitted", "discharge_initiated"):
            raise PadConflict("This patient has already been discharged.")

        def same(column, value):
            return column.is_(None) if value is None else column == value

        if not new:
            found = (
                await self.session.execute(
                    select(PadDocument).where(
                        PadDocument.patient_id == patient.id,
                        PadDocument.document_type == document_type,
                        PadDocument.status == PadStatus.DRAFT,
                        PadDocument.author_id == user.id,
                        same(PadDocument.consultation_id, consultation.id if consultation else None),
                        same(PadDocument.admission_id, admission.id if admission else None),
                        same(PadDocument.surgery_id, surgery.id if surgery else None),
                        same(PadDocument.order_item_id, order_item.id if order_item else None),
                    ).order_by(PadDocument.created_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if found is not None:
                return found

        department = (
            (surgery.department if surgery else None)
            or (admission.department if admission else None)
            or (consultation.department if consultation else None)
            or user.department
        )
        layout, sections, _scope = await self.resolve_layout(
            document_type, department=department, user_id=user.id
        )
        values = forms.prefill(
            document_type,
            today=local_today(),
            admission={
                "admitted_on": to_local(admission.admitted_at).date(),
                "discharged_on": to_local(admission.discharged_at).date() if admission.discharged_at else None,
                "diagnosis": admission.final_diagnosis or admission.provisional_diagnosis,
            } if admission else None,
            surgery={
                "procedure": surgery.operation_name, "side": surgery.laterality,
                "diagnosis": surgery.diagnosis, "surgeon": surgery.surgeon_name,
                "anaesthesia": surgery.anaesthesia_type,
            } if surgery else None,
            order_item={
                "name": order_item.name,
                "site": order_item.specimen_or_site,
                "indication": order.provisional_diagnosis or order.clinical_notes,
            } if order_item else None,
        )
        document = PadDocument(
            document_type=document_type,
            title=spec.label,
            patient_id=patient.id,
            consultation_id=consultation.id if consultation else None,
            admission_id=admission.id if admission else None,
            surgery_id=surgery.id if surgery else None,
            order_item_id=order_item.id if order_item else None,
            department=department,
            layout_id=layout.id if layout else None,
            layout_revision=layout.revision if layout else 0,
            sections=sections,
            values=rules.clean_values(sections, values),
            provenance={},
            status=PadStatus.DRAFT,
            author_id=user.id,
            author_name=user.full_name,
            group_id=uuid.uuid4(),
            version=1,
        )
        self.session.add(document)
        await self.session.commit()
        return document

    async def _next_serial(self, prefix: str) -> str:
        """MC26-00001: sequential per prefix per year, from the shared counter."""
        from app.models.emr import DocumentCounter

        period = f"{local_today().year}"
        scope = prefix.lower()
        lookup = (
            select(DocumentCounter)
            .where(DocumentCounter.scope == scope, DocumentCounter.period == period)
            .with_for_update()
        )
        counter = (await self.session.execute(lookup)).scalar_one_or_none()
        if counter is None:
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope=scope, period=period, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = (await self.session.execute(lookup)).scalar_one()
        counter.last_value += 1
        await self.session.flush()
        return f"{prefix}{local_today().year % 100:02d}-{counter.last_value:05d}"

    async def _mark_reported(self, order_item_id: uuid.UUID) -> None:
        """A signed radiology report completes its order item, and perhaps its order."""
        from app.services.investigation_service import mark_order_item_reported

        await mark_order_item_reported(self.session, order_item_id)

    async def radiology_worklist(self, *, include_reported: bool = False, limit: int = 200) -> List[Dict[str, Any]]:
        """Imaging studies ordered and waiting for a report, oldest first."""
        from app.models.enums import InvestigationCategory, OrderStatus
        from app.models.investigation import InvestigationOrder, InvestigationOrderItem

        statement = (
            select(InvestigationOrderItem, InvestigationOrder, Patient)
            .join(InvestigationOrder, InvestigationOrder.id == InvestigationOrderItem.order_id)
            .join(Patient, Patient.id == InvestigationOrder.patient_id)
            .where(
                InvestigationOrderItem.category.in_(
                    [InvestigationCategory(value) for value in forms.IMAGING_CATEGORIES]
                ),
                InvestigationOrder.status.notin_([OrderStatus.DRAFT, OrderStatus.CANCELLED]),
            )
            .order_by(InvestigationOrder.created_at)
            .limit(limit)
        )
        if not include_reported:
            statement = statement.where(InvestigationOrderItem.reported.is_(False))
        rows = (await self.session.execute(statement)).all()
        reports: Dict[uuid.UUID, PadDocument] = {}
        if rows:
            found = (await self.session.execute(
                select(PadDocument).where(
                    PadDocument.order_item_id.in_([item.id for item, _order, _patient in rows]),
                    PadDocument.status != PadStatus.SUPERSEDED,
                ).order_by(PadDocument.created_at)
            )).scalars()
            for document in found:
                current = reports.get(document.order_item_id)
                if current is None or document.status == PadStatus.SIGNED:
                    reports[document.order_item_id] = document
        return [
            {
                "item_id": item.id,
                "code": item.code,
                "name": item.name,
                "category": item.category.value,
                "site": item.specimen_or_site,
                "order_id": order.id,
                "consultation_id": order.consultation_id,
                "ordered_at": order.issued_at or order.created_at,
                "ordered_by_name": order.ordered_by_name,
                "priority": order.priority.value,
                "clinical_notes": order.clinical_notes,
                "provisional_diagnosis": order.provisional_diagnosis,
                "reported": item.reported,
                "patient": {"id": patient.id, "name": patient.name, "uhid": patient.uhid,
                            "age": patient.age, "gender": patient.gender.value},
                "report": {
                    "id": reports[item.id].id,
                    "status": reports[item.id].status.value,
                    "serial_number": reports[item.id].serial_number,
                    "author_name": reports[item.id].author_name,
                } if item.id in reports else None,
            }
            for item, order, patient in rows
        ]

    async def record_paper_signed(self, document_id: uuid.UUID, *, user: User) -> PadDocument:
        """Record that the patient's signed paper copy of a consent form came back."""
        document = (
            await self.session.execute(
                select(PadDocument).where(PadDocument.id == document_id).with_for_update()
            )
        ).scalar_one_or_none()
        if document is None:
            raise PadNotFound("That document no longer exists.")
        spec = type_spec(document.document_type)
        if spec is None or spec.family != "consent":
            raise PadError("Only a consent form has a signed paper copy to record.")
        if document.status == PadStatus.DRAFT:
            raise PadConflict(
                "Sign the form in the system first, then print it for the patient to sign."
            )
        if document.status == PadStatus.SUPERSEDED:
            raise PadConflict(
                "A corrected version of this form exists. The patient must sign the corrected version."
            )
        if document.paper_signed_at is not None:
            raise PadConflict(
                f"Already recorded by {document.paper_signed_by_name} on "
                f"{document.paper_signed_at:%d %b %Y}."
            )
        document.paper_signed_at = _now()
        document.paper_signed_by_name = user.full_name
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def open_for_surgery(
        self, surgery_id: uuid.UUID, document_type: str, *, user: User
    ) -> PadDocument:
        """A theatre note for one case: its draft, its signed copy, or a new draft.

        A new draft is filled from the booking — the operation with its side,
        the diagnosis, the team — and from the admission's allergies, so the
        side on the operation note is the side that was booked, not the side
        someone remembered.
        """
        from app.models.theatre import Surgery

        spec = type_spec(document_type)
        if spec is None:
            raise PadNotFound(f"There is no document type called {document_type!r}.")
        if spec.scope != "surgery":
            raise PadError(f"{spec.label} is not a theatre note.")

        surgery = (
            await self.session.execute(
                select(Surgery).where(Surgery.id == surgery_id).with_for_update()
            )
        ).scalar_one_or_none()
        if surgery is None:
            raise PadNotFound("Surgery not found.")

        existing = select(PadDocument).where(
            PadDocument.surgery_id == surgery_id,
            PadDocument.document_type == document_type,
        )
        found = (
            await self.session.execute(existing.where(PadDocument.status == PadStatus.DRAFT).limit(1))
        ).scalar_one_or_none()
        if found is None:
            found = (
                await self.session.execute(
                    existing.where(PadDocument.status == PadStatus.SIGNED)
                    .order_by(PadDocument.signed_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if found is not None:
            await self.session.commit()
            return found

        if surgery.status.value == "cancelled":
            await self.session.rollback()
            raise PadConflict(
                "This case was cancelled. Its notes can be read and corrected, but new ones "
                "cannot be started."
            )

        admission = (
            await self.session.get(Admission, surgery.admission_id) if surgery.admission_id else None
        )
        team = [f"Surgeon: {surgery.surgeon_name}"]
        if surgery.assistants:
            team.append(f"Assistants: {', '.join(surgery.assistants)}")
        if surgery.anaesthetist_name:
            team.append(f"Anaesthetist: {surgery.anaesthetist_name}")
        if surgery.anaesthesia_type:
            team.append(f"Anaesthesia: {surgery.anaesthesia_type}")

        layout, sections, _scope = await self.resolve_layout(
            document_type, department=surgery.department, user_id=user.id
        )
        values, provenance = rules.draft_from_record(
            sections,
            {
                "procedure": f"{surgery.operation_name} — {surgery.laterality}",
                "diagnosis": surgery.diagnosis,
                "team": team,
                "allergies": (admission.allergies if admission else None) or [],
                "reason_for_admission": admission.reason_for_admission if admission else None,
                "provisional_diagnosis": admission.provisional_diagnosis if admission else None,
            },
        )
        document = PadDocument(
            document_type=document_type,
            title=f"{spec.label} — {surgery.ot_number}",
            patient_id=surgery.patient_id,
            admission_id=surgery.admission_id,
            surgery_id=surgery.id,
            department=surgery.department,
            layout_id=layout.id if layout else None,
            layout_revision=layout.revision if layout else 0,
            sections=sections,
            values=values,
            provenance=provenance,
            status=PadStatus.DRAFT,
            author_id=user.id,
            author_name=user.full_name,
            group_id=uuid.uuid4(),
            version=1,
        )
        self.session.add(document)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            found = (
                await self.session.execute(existing.where(PadDocument.status == PadStatus.DRAFT).limit(1))
            ).scalar_one_or_none()
            if found is None:
                raise
            return found
        return document

    async def draft_discharge_with_ai(
        self, document_id: uuid.UUID, *, user: User
    ) -> Tuple[PadDocument, List[str], List[str]]:
        """Fill the empty sections of a discharge summary from the ward record.

        Only empty sections are filled. A doctor who has already written the
        course in hospital keeps their words. Returns the document, the titles
        of the sections filled, and whatever the model reported as uncertain or
        missing — shown to the doctor, never saved into the summary.
        """
        from sqlalchemy.orm import selectinload

        from app.ai.ipd_documentation import DischargeSummaryService, build_stay_record
        from app.ai.pipeline.base_service import StageError

        document = await self.get(document_id)
        self._require_draft(document)
        if document.document_type != "ipd_discharge_summary" or document.admission_id is None:
            raise PadError("Only a discharge summary can be drafted from the ward record.")

        admission = (
            await self.session.execute(
                select(Admission)
                .options(
                    selectinload(Admission.occupancies),
                    selectinload(Admission.vitals),
                    selectinload(Admission.notes),
                    selectinload(Admission.medications),
                )
                .where(Admission.id == document.admission_id)
            )
        ).scalar_one()
        patient = await self.session.get(Patient, admission.patient_id)

        # Signed pad documents are part of the stay: the progress notes are
        # where the course in hospital was actually written down.
        signed_documents = (
            await self.session.execute(
                select(PadDocument)
                .where(
                    PadDocument.admission_id == admission.id,
                    PadDocument.status == PadStatus.SIGNED,
                    PadDocument.document_type != "ipd_discharge_summary",
                )
                .order_by(PadDocument.signed_at)
            )
        ).scalars().all()

        notes = [
            {"created_at": note.created_at.isoformat(), "note_type": note.note_type.value,
             "author_name": note.author_name, "content": note.content}
            for note in admission.notes
        ] + [
            {"created_at": (item.signed_at or item.created_at).isoformat(),
             "note_type": item.title, "author_name": item.signed_by_name or item.author_name,
             "content": rules.as_text(item.sections, item.values or {})}
            for item in signed_documents
        ]
        notes.sort(key=lambda entry: entry["created_at"])

        record = build_stay_record(
            patient={"name": patient.name, "age": patient.age,
                     "gender": patient.gender.value, "uhid": patient.uhid} if patient else {},
            admission={
                "ip_number": admission.ip_number,
                "admitted_at": admission.admitted_at.isoformat(),
                "discharged_at": admission.discharged_at.isoformat() if admission.discharged_at else None,
                "admitting_doctor_name": admission.admitting_doctor_name,
                "reason_for_admission": admission.reason_for_admission,
                "provisional_diagnosis": admission.provisional_diagnosis,
                "final_diagnosis": admission.final_diagnosis,
                "allergies": admission.allergies or [],
            },
            occupancies=[
                {"ward_name": item.ward_name, "bed_label": item.bed_label,
                 "started_at": item.started_at.isoformat(),
                 "ended_at": item.ended_at.isoformat() if item.ended_at else None}
                for item in admission.occupancies
            ],
            vitals=[
                {"recorded_at": item.recorded_at.isoformat(),
                 "respiratory_rate": item.respiratory_rate, "spo2_percent": item.spo2_percent,
                 "systolic_bp": item.systolic_bp, "pulse": item.pulse,
                 "temperature_c": item.temperature_c, "news2_score": item.news2_score,
                 "news2_risk": item.news2_risk}
                for item in admission.vitals
            ],
            notes=notes,
            medications=[
                {"drug_name": item.drug_name, "strength": item.strength, "dose": item.dose,
                 "route": item.route.value, "frequency_code": item.frequency_code,
                 "status": item.status.value, "instructions": item.instructions}
                for item in admission.medications
            ],
        )

        try:
            draft = await DischargeSummaryService().draft(record, tag=admission.ip_number)
        except StageError as exc:
            raise PadUnavailable(
                f"The summary could not be drafted right now ({exc}). Write it directly; "
                "nothing on the pad has changed."
            ) from exc

        def medicine(item) -> str:
            parts = [item.name, item.dose, item.route, item.frequency]
            if item.duration:
                parts.append(f"for {item.duration}")
            if item.instructions:
                parts.append(f"({item.instructions})")
            return " ".join(part for part in parts if part)

        proposed = rules.clean_values(document.sections, {
            "presenting_complaint": {"text": draft.presenting_complaint},
            "hospital_course": {"text": "\n\n".join(
                part for part in (draft.history_summary, draft.hospital_course) if part
            )},
            "significant_findings": {"text": draft.significant_findings},
            "procedures": {"items": list(draft.procedures_performed)},
            # The condition itself is a choice the doctor makes; the model's
            # words go in the notes beside it.
            "condition_at_discharge": {"fields": {"notes": draft.condition_at_discharge}},
            "discharge_medications": {"items": [medicine(item) for item in draft.discharge_medications]},
            "diet_and_activity": {"text": draft.diet_and_activity},
            "follow_up": {"fields": {"notes": draft.follow_up_instructions}},
            "warning_signs": {"items": list(draft.warning_signs)},
        })

        values = dict(document.values or {})
        provenance = dict(document.provenance or {})
        drafted_at = _now().isoformat()
        filled: List[str] = []
        for section in document.sections:
            key = section["key"]
            if key not in proposed or rules.is_empty(section, proposed[key]):
                continue
            if not rules.is_empty(section, values.get(key)):
                continue
            values[key] = proposed[key]
            provenance[key] = {"source": "ai:discharge_summary", "drafted_at": drafted_at}
            filled.append(section["title"])

        document.values = values
        document.provenance = provenance
        await self.session.commit()
        await self.session.refresh(document)
        logger.info(
            "discharge_summary_drafted",
            extra={"document_id": str(document.id), "filled": len(filled), "by": user.full_name},
        )
        return document, filled, list(draft.uncertain_or_missing or [])

    def _require_draft(self, document: PadDocument) -> None:
        if document.status != PadStatus.DRAFT:
            raise PadConflict(
                "This document is signed and cannot be changed. Amend it to make a "
                "corrected version."
            )

    @staticmethod
    def _same_moment(first: Optional[datetime], second: Optional[datetime]) -> bool:
        if first is None or second is None:
            return True
        # Browsers round-trip timestamps at millisecond precision; Postgres
        # stores microseconds. Equal to the millisecond is the same save.
        return abs((first - second).total_seconds()) < 0.001

    async def save_values(
        self,
        document_id: uuid.UUID,
        *,
        values: Dict[str, Any],
        base_updated_at: Optional[datetime],
        user: User,
    ) -> PadDocument:
        """Autosave. Refused if the browser's copy is out of date."""
        document = (
            await self.session.execute(
                select(PadDocument).where(PadDocument.id == document_id).with_for_update()
            )
        ).scalar_one_or_none()
        if document is None:
            raise PadNotFound("That document no longer exists.")
        self._require_draft(document)
        if not self._same_moment(base_updated_at, document.updated_at):
            raise PadConflict(
                "Someone else has changed this pad since you opened it. Reload to see "
                "their changes before saving yours."
            )

        cleaned = rules.clean_values(document.sections, values)
        # Keep every section the browser did not send: a save from a stale
        # form missing a section must not erase it.
        merged = {**(document.values or {}), **cleaned}

        provenance = dict(document.provenance or {})
        for key, origin in list(provenance.items()):
            if (document.values or {}).get(key) != merged.get(key) and not origin.get("edited"):
                provenance[key] = {**origin, "edited": True, "edited_by": user.full_name}

        document.values = merged
        document.provenance = provenance
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def arrange(
        self,
        document_id: uuid.UUID,
        *,
        arrangement: List[Dict[str, Any]],
        user: User,
    ) -> PadDocument:
        """Reorder this document's sections and set what shows and prints.

        Changes this document only. A doctor unticking the differentials on
        one patient's slip has not changed the hospital's pad.
        """
        document = await self.get(document_id)
        self._require_draft(document)

        by_key = {section["key"]: section for section in document.sections}
        requested = [item.get("key") for item in arrangement]
        if sorted(requested) != sorted(by_key):
            raise PadError(
                "The arrangement must list every section of this document exactly once."
            )

        arranged = []
        for item in arrangement:
            section = dict(by_key[item["key"]])
            section["visible_in_pad"] = bool(item.get("visible_in_pad", section["visible_in_pad"]))
            section["visible_in_print"] = bool(
                item.get("visible_in_print", section["visible_in_print"])
            )
            arranged.append(section)

        document.sections = arranged
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def discard(self, document_id: uuid.UUID, *, user: User) -> None:
        document = await self.get(document_id)
        self._require_draft(document)
        await self.session.delete(document)
        await self.session.commit()
        logger.info("pad_draft_discarded", extra={"document_id": str(document_id), "by": user.full_name})

    # ------------------------------------------------------------- signing

    # ------------------------------------------------ what a pad issues
    def _rows(self, document: PadDocument, kind: str, key: str) -> List[Dict[str, Any]]:
        """Every accepted row of one section kind, in the order written.

        Suggestions are ignored on purpose: only what the doctor accepted is
        prescribed or ordered.
        """
        rows: List[Dict[str, Any]] = []
        for section in document.sections:
            if section["kind"] != kind:
                continue
            value = (document.values or {}).get(section["key"]) or {}
            rows.extend(value.get(key) or [])
        return rows

    def _section_items(self, document: PadDocument, key: str) -> List[str]:
        value = (document.values or {}).get(key) or {}
        return [item for item in (value.get("items") or []) if item]

    async def _check_prescribing(
        self, document: PadDocument, acknowledged_alerts: List[Dict[str, Any]]
    ) -> None:
        """Refuse the signature while a serious medication warning stands.

        Checked before anything is written, not after: a signature is the
        doctor taking responsibility, and it must not be possible to sign and
        then be told the patient is allergic to what was just prescribed.
        """
        medicines = self._rows(document, "medicines", "medicines")
        if not medicines:
            return
        from app.prescriptions import safety

        prescriptions = PrescriptionService(self.session)
        patient = await self.session.get(Patient, document.patient_id)
        alerts = safety.run_all(
            medicines,
            allergies=await prescriptions._known_allergies(document.patient_id),
            pregnancy_possible=await prescriptions._pregnancy_possible(
                document.patient_id, patient
            ),
        )
        acknowledged = {
            (item.get("kind"), tuple(sorted(item.get("medicines") or [])))
            for item in acknowledged_alerts or []
        }
        standing = [
            alert for alert in safety.blocking_alerts(alerts)
            if (alert.kind, tuple(sorted(alert.medicines))) not in acknowledged
        ]
        if standing:
            raise PadError(
                "Acknowledge these safety warnings before signing: "
                + "; ".join(alert.description for alert in standing)
            )

    async def _issue_from_pad(
        self, document: PadDocument, *, user: User, acknowledged_alerts: List[Dict[str, Any]]
    ) -> None:
        """Turn the signed pad into the prescription and the orders it records.

        The pad is the only place the doctor writes; the prescription and the
        investigation order are made from it, so the two can never disagree.
        Both are linked back to the document.
        """
        medicines = self._rows(document, "medicines", "medicines")
        investigations = self._rows(document, "investigations", "investigations")
        if not medicines and not investigations:
            return

        department = document.department or user.department or Department.ORTHOPEDICS
        signer = (
            await self.session.execute(
                select(Consultant).where(Consultant.user_id == user.id)
            )
        ).scalar_one_or_none()

        if medicines and document.prescription_id is None:
            diagnosis = "; ".join(self._section_items(document, "diagnosis"))
            if not diagnosis:
                raise PadError(
                    "Write the diagnosis before signing — a prescription cannot be "
                    "issued without one."
                )
            follow_up = ((document.values or {}).get("follow_up") or {}).get("fields") or {}
            review_on = _review_date(follow_up)
            prescription = await PrescriptionService(self.session).create(
                patient_id=document.patient_id,
                consultation_id=document.consultation_id,
                department=department,
                doctor_id=user.id,
                doctor_name=user.full_name,
                doctor_qualification=signer.qualification if signer else None,
                doctor_registration=signer.registration_number if signer else None,
                medicines=medicines,
                diagnosis=diagnosis,
                cause=None,
                chief_complaint="; ".join(self._section_items(document, "complaints")) or None,
                clinical_findings=(
                    "; ".join(self._section_items(document, "examination")) or None
                ),
                investigations=[row["name"] for row in investigations],
                general_instructions=(
                    "; ".join(self._section_items(document, "advice")) or None
                ),
                follow_up_notes=follow_up.get("notes"),
                follow_up_date=review_on,
                dictation_transcript=None,
                acknowledged_alerts=acknowledged_alerts or [],
                issue=True,
            )
            document.prescription_id = prescription.id

        # Only a test that resolves in the catalogue can be ordered. One typed
        # as free text still prints on the pad as advice, but the laboratory
        # never receives an order it cannot act on.
        codes = [row["code"] for row in investigations if row.get("code")]
        if codes and document.investigation_order_id is None:
            from app.services.investigation_service import (
                InvestigationError,
                InvestigationService,
            )
            from app.models.enums import InvestigationPriority

            try:
                order = await InvestigationService(self.session).create_order(
                    patient_id=document.patient_id,
                    consultation_id=document.consultation_id,
                    department=department,
                    codes=codes,
                    priority=InvestigationPriority.ROUTINE,
                    clinical_notes=None,
                    provisional_diagnosis=(
                        "; ".join(self._section_items(document, "diagnosis")) or None
                    ),
                    doctor_id=user.id,
                    doctor_name=user.full_name,
                    item_instructions={
                        row["code"]: row["note"]
                        for row in investigations
                        if row.get("code") and row.get("note")
                    },
                )
            except InvestigationError as exc:
                raise PadError(str(exc)) from exc
            document.investigation_order_id = order.id

    async def sign(
        self,
        document_id: uuid.UUID,
        *,
        user: User,
        acknowledged_alerts: Optional[List[Dict[str, Any]]] = None,
    ) -> PadDocument:
        document = (
            await self.session.execute(
                select(PadDocument).where(PadDocument.id == document_id).with_for_update()
            )
        ).scalar_one_or_none()
        if document is None:
            raise PadNotFound("That document no longer exists.")
        self._require_draft(document)

        if all(
            rules.is_empty(section, (document.values or {}).get(section["key"]))
            for section in document.sections
        ):
            raise PadError("There is nothing written on this document to sign.")

        missing = [
            f"{section['title']}: {spec['label']}"
            for section in document.sections
            if section["kind"] == "fields"
            for spec in section.get("fields", [])
            if spec.get("required")
            and ((document.values or {}).get(section["key"], {}).get("fields") or {}).get(spec["key"])
            in (None, "", [], False)
        ]
        if missing:
            raise PadError("Required before signing — " + "; ".join(missing[:5]))

        await self._check_prescribing(document, acknowledged_alerts or [])

        spec = type_spec(document.document_type)
        if spec is not None and spec.family:
            from app.core.clock import to_local

            patient = await self.session.get(Patient, document.patient_id)
            admission = (
                await self.session.get(Admission, document.admission_id) if document.admission_id else None
            )
            problems = forms.check(
                document.document_type,
                document.values or {},
                today=local_today(),
                patient_age=patient.age if patient else None,
                admission={
                    "admitted_on": to_local(admission.admitted_at).date(),
                    "discharged_on": to_local(admission.discharged_at).date() if admission.discharged_at else None,
                } if admission else None,
            )
            if problems:
                raise PadError("Cannot sign yet — " + "; ".join(problems[:5]))
            if document.serial_number is None:
                original = (
                    await self.session.get(PadDocument, document.supersedes_id)
                    if document.supersedes_id else None
                )
                document.serial_number = (
                    original.serial_number
                    if original is not None and original.serial_number
                    else await self._next_serial(forms.SERIAL_PREFIX[spec.family])
                )
            if document.order_item_id is not None:
                await self._mark_reported(document.order_item_id)

        if document.supersedes_id is not None:
            original = await self.session.get(PadDocument, document.supersedes_id)
            if original is not None and original.status == PadStatus.SIGNED:
                original.status = PadStatus.SUPERSEDED

        document.status = PadStatus.SIGNED
        document.signed_by_id = user.id
        document.signed_by_name = user.full_name
        document.signed_at = _now()

        # The signed discharge summary is where the final diagnosis is decided,
        # so the admission takes it from there rather than from a box someone
        # filled in earlier on the ward board.
        if document.document_type == "ipd_discharge_summary" and document.admission_id:
            admission = await self.session.get(Admission, document.admission_id)
            diagnoses = ((document.values or {}).get("final_diagnosis") or {}).get("items") or []
            if admission is not None and diagnoses:
                admission.final_diagnosis = "; ".join(diagnoses)[:2000]

        await self._issue_from_pad(
            document, user=user, acknowledged_alerts=acknowledged_alerts or []
        )

        await self._learn(document)
        await self.session.commit()
        await self.session.refresh(document)
        logger.info(
            "pad_signed",
            extra={
                "document_id": str(document.id),
                "version": document.version,
                "by": user.full_name,
            },
        )
        return document

    async def amend(self, document_id: uuid.UUID, *, reason: str, user: User) -> PadDocument:
        """Start a corrected version of a signed document."""
        original = await self.get(document_id)
        if original.status == PadStatus.DRAFT:
            raise PadConflict("This document is not signed yet — edit it directly.")
        if original.status == PadStatus.SUPERSEDED:
            raise PadConflict(
                "A newer version of this document exists. Amend the latest version instead."
            )
        reason = (reason or "").strip()
        if len(reason) < 5:
            raise PadError("Say what is being corrected. The reason is kept with the record.")

        pending = (
            await self.session.execute(
                select(PadDocument).where(
                    PadDocument.group_id == original.group_id,
                    PadDocument.status == PadStatus.DRAFT,
                )
            )
        ).scalar_one_or_none()
        if pending is not None:
            return pending

        amendment = PadDocument(
            document_type=original.document_type,
            title=original.title,
            patient_id=original.patient_id,
            consultation_id=original.consultation_id,
            admission_id=original.admission_id,
            department=original.department,
            layout_id=original.layout_id,
            layout_revision=original.layout_revision,
            sections=[dict(section) for section in original.sections],
            values=dict(original.values or {}),
            provenance=dict(original.provenance or {}),
            status=PadStatus.DRAFT,
            author_id=user.id,
            author_name=user.full_name,
            group_id=original.group_id,
            version=original.version + 1,
            supersedes_id=original.id,
            amendment_reason=reason,
        )
        self.session.add(amendment)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise PadConflict(
                "A draft is already open for this consultation. Finish or discard it first."
            ) from exc
        logger.info(
            "pad_amendment_started",
            extra={"document_id": str(original.id), "by": user.full_name},
        )
        return amendment

    # ======================================================== the three habits
    async def previous_visit(self, document_id: uuid.UUID) -> Optional[PadDocument]:
        """The patient's last signed document of the same kind, from another visit."""
        document = await self.get(document_id)
        return (
            await self.session.execute(
                select(PadDocument)
                .where(
                    PadDocument.patient_id == document.patient_id,
                    PadDocument.document_type == document.document_type,
                    PadDocument.status == PadStatus.SIGNED,
                    PadDocument.group_id != document.group_id,
                )
                .order_by(PadDocument.signed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def copy_previous(self, document_id: uuid.UUID, *, user: User) -> PadDocument:
        document = await self.get(document_id)
        self._require_draft(document)
        previous = await self.previous_visit(document_id)
        if previous is None:
            raise PadNotFound("This patient has no earlier signed visit to copy from.")

        carried = rules.carry_forward(document.sections, previous.values or {})
        if not carried:
            raise PadError(
                "Nothing on the previous visit is set to carry forward. Diagnosis and "
                "advice carry by default; the layout decides the rest."
            )
        document.values = rules.merge_template(
            document.sections, document.values or {}, carried, replace=False
        )
        provenance = dict(document.provenance or {})
        for key in carried:
            provenance[key] = {
                "source": "previous_visit",
                "document_id": str(previous.id),
                "signed_at": previous.signed_at.isoformat() if previous.signed_at else None,
            }
        document.provenance = provenance
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def list_templates(
        self, document_type: str, *, department: Optional[Department], user: User
    ) -> List[PadTemplate]:
        self._require_type(document_type)
        mine_or_shared = or_(PadTemplate.owner_id == user.id, PadTemplate.owner_id.is_(None))
        in_department = or_(
            PadTemplate.department.is_(None),
            PadTemplate.department == department if department else PadTemplate.department.is_(None),
        )
        return list(
            (
                await self.session.execute(
                    select(PadTemplate)
                    .where(
                        PadTemplate.document_type == document_type,
                        mine_or_shared,
                        in_department,
                    )
                    .order_by(PadTemplate.use_count.desc(), PadTemplate.name)
                )
            ).scalars()
        )

    async def save_template(
        self,
        document_id: uuid.UUID,
        *,
        name: str,
        description: Optional[str],
        shared: bool,
        user: User,
    ) -> PadTemplate:
        """Save what is on this pad as a template for other patients.

        AI sections are left out. They were drafted from one patient's intake
        conversation, and a template carrying them would put that patient's
        history into the next patient's record.
        """
        document = await self.get(document_id)
        name = (name or "").strip()
        if not name:
            raise PadError("Give the template a name.")

        reusable = [section for section in document.sections if section["kind"] != "ai"]
        values = {
            key: value
            for key, value in rules.clean_values(reusable, document.values or {}).items()
            if not rules.is_empty(
                next(section for section in reusable if section["key"] == key), value
            )
        }
        if not values:
            raise PadError(
                "There is nothing on this pad a template could reuse. AI-drafted "
                "sections are never saved into templates."
            )

        template = PadTemplate(
            document_type=document.document_type,
            department=document.department,
            owner_id=None if shared else user.id,
            owner_name=user.full_name,
            name=name[:160],
            description=(description or "").strip() or None,
            values=values,
        )
        self.session.add(template)
        await self.session.commit()
        return template

    async def apply_template(
        self,
        document_id: uuid.UUID,
        *,
        template_id: uuid.UUID,
        replace: bool,
        user: User,
    ) -> PadDocument:
        document = await self.get(document_id)
        self._require_draft(document)
        template = await self.session.get(PadTemplate, template_id)
        if template is None:
            raise PadNotFound("That template no longer exists.")
        if template.owner_id not in (None, user.id):
            raise PadForbidden("That template belongs to another doctor.")
        if template.document_type != document.document_type:
            raise PadError("That template is for a different kind of document.")

        patient = await self.session.get(Patient, document.patient_id)
        context = rules.variable_context(patient, local_today())
        incoming = rules.apply_variables(template.values or {}, context)

        document.values = rules.merge_template(
            document.sections, document.values or {}, incoming, replace=replace
        )
        provenance = dict(document.provenance or {})
        for key in incoming:
            if any(section["key"] == key for section in document.sections):
                provenance[key] = {
                    "source": "template",
                    "template_id": str(template.id),
                    "name": template.name,
                }
        document.provenance = provenance

        template.use_count += 1
        template.last_used_at = _now()
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def delete_template(self, template_id: uuid.UUID, *, user: User, may_manage_shared: bool) -> None:
        template = await self.session.get(PadTemplate, template_id)
        if template is None:
            raise PadNotFound("That template no longer exists.")
        if template.owner_id is None and not may_manage_shared:
            raise PadForbidden("Only a doctor who manages templates can remove a shared one.")
        if template.owner_id is not None and template.owner_id != user.id:
            raise PadForbidden("That template belongs to another doctor.")
        await self.session.delete(template)
        await self.session.commit()

    # ============================================================= catalogue
    async def _learn(self, document: PadDocument) -> None:
        phrases = rules.catalogue_phrases(document.sections, document.values or {})
        if not phrases:
            return
        department = document.department.value if document.department else ""
        moment = _now()
        seen = set()
        for category, text in phrases:
            normalized = rules.normalize_phrase(text)
            if (category, normalized) in seen:
                continue
            seen.add((category, normalized))
            statement = insert(PadCatalogueEntry).values(
                id=uuid.uuid4(),
                category=category,
                department=department,
                text=text,
                normalized=normalized,
                use_count=1,
                last_used_at=moment,
            )
            statement = statement.on_conflict_do_update(
                constraint="uq_pad_catalogue_phrase",
                set_={
                    "use_count": PadCatalogueEntry.use_count + 1,
                    "last_used_at": moment,
                    # The most recent spelling wins, so a phrase corrected
                    # from "Bilat OA" to "B/L OA knee" is offered corrected.
                    "text": statement.excluded.text,
                },
            )
            await self.session.execute(statement)

    async def suggest(
        self,
        category: str,
        *,
        query: str,
        department: Optional[Department],
        limit: int = 12,
    ) -> List[PadCatalogueEntry]:
        """Phrases staff have used before, best first.

        A phrase that starts with what was typed beats one that merely
        contains it, and within each the most used wins. The department's own
        phrases and hospital-wide ones are both offered.
        """
        term = rules.normalize_phrase(query)
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        departments = [""] + ([department.value] if department else [])

        statement = select(PadCatalogueEntry).where(
            PadCatalogueEntry.category == category,
            PadCatalogueEntry.department.in_(departments),
        )
        if term:
            statement = statement.where(
                PadCatalogueEntry.normalized.like(f"%{escaped}%", escape="\\")
            ).order_by(
                case((PadCatalogueEntry.normalized.like(f"{escaped}%", escape="\\"), 0), else_=1),
                PadCatalogueEntry.use_count.desc(),
                PadCatalogueEntry.last_used_at.desc(),
            )
        else:
            statement = statement.order_by(
                PadCatalogueEntry.use_count.desc(), PadCatalogueEntry.last_used_at.desc()
            )

        rows = list((await self.session.execute(statement.limit(limit * 2))).scalars())
        unique: List[PadCatalogueEntry] = []
        seen = set()
        for row in rows:
            if row.normalized in seen:
                continue
            seen.add(row.normalized)
            unique.append(row)
        return unique[:limit]

    # ================================================================ history
    async def list_documents(
        self,
        *,
        patient_id: Optional[uuid.UUID],
        consultation_id: Optional[uuid.UUID],
        document_type: Optional[str],
        include_superseded: bool = False,
        admission_id: Optional[uuid.UUID] = None,
        surgery_id: Optional[uuid.UUID] = None,
    ) -> List[PadDocument]:
        if all(item is None for item in (patient_id, consultation_id, admission_id, surgery_id)):
            raise PadError("Say which patient, consultation, admission or surgery.")
        statement = select(PadDocument)
        if patient_id is not None:
            statement = statement.where(PadDocument.patient_id == patient_id)
        if consultation_id is not None:
            statement = statement.where(PadDocument.consultation_id == consultation_id)
        if admission_id is not None:
            statement = statement.where(PadDocument.admission_id == admission_id)
        if surgery_id is not None:
            statement = statement.where(PadDocument.surgery_id == surgery_id)
        if document_type:
            statement = statement.where(PadDocument.document_type == document_type)
        if not include_superseded:
            statement = statement.where(PadDocument.status != PadStatus.SUPERSEDED)
        statement = statement.order_by(PadDocument.created_at.desc())
        return list((await self.session.execute(statement)).scalars())

    async def mark_printed(self, document: PadDocument) -> int:
        """Count a print. Returns the count, so the caller can stamp a duplicate.

        Drafts are not counted: a draft is printed to read, and the first
        print of the signed document is still the original.
        """
        if document.status == PadStatus.DRAFT:
            return 0
        document.print_count = (document.print_count or 0) + 1
        await self.session.commit()
        return document.print_count
