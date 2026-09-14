"""Inpatient department.

Design notes worth reading before changing anything here:

**A bed's occupancy is a table, not a column.** `Bed.status` says what is true
now; `BedOccupancy` says what was true then. Billing, infection tracing and any
question about who was in which bed on a given night all depend on the history,
and a status column alone silently loses it the moment a patient is moved.

**Charges are posted rows, not computed on demand.** A bed-day charge is
written once, for a specific date, with the rate that applied then. Recomputing
the bill from the tariff at discharge would silently reprice the whole stay
whenever the tariff changed mid-admission — which for a three-week stay is
likely.

**Money is integer paise**, matching the OPD billing layer exactly. See
app/billing/money.py.

**Vitals carry their own score.** The NEWS2 total is stored on the row rather
than recalculated for display, so the number a nurse acted on at 2am is the
number visible in the record afterwards, even if the scoring rules are later
revised.
"""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AdmissionStatus,
    AdmissionType,
    BedStatus,
    ChargeCategory,
    Department,
    DischargeType,
    MedicationRouteIPD,
    MedicationStatus,
    NoteType,
    WardType,
)

_VALUES = lambda e: [m.value for m in e]  # noqa: E731


class Ward(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A physical ward. Its rate is the default for beds inside it."""

    __tablename__ = "wards"

    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    ward_type: Mapped[WardType] = mapped_column(
        SAEnum(WardType, name="ward_type", values_callable=_VALUES), nullable=False
    )
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES), index=True
    )
    floor: Mapped[Optional[str]] = mapped_column(String(32))
    daily_rate_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Nursing and RMO charges that accrue per day alongside the bed itself.
    nursing_rate_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    beds: Mapped[List["Bed"]] = relationship(
        back_populates="ward", cascade="all, delete-orphan", order_by="Bed.label"
    )


class Bed(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "beds"
    __table_args__ = (
        UniqueConstraint("ward_id", "label", name="uq_bed_ward_label"),
        Index("ix_beds_status", "status"),
    )

    ward_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wards.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[BedStatus] = mapped_column(
        SAEnum(BedStatus, name="bed_status", values_callable=_VALUES),
        nullable=False, default=BedStatus.VACANT,
    )
    # Overrides the ward rate for this bed only (a private room with a
    # different tariff inside a shared ward, for instance).
    rate_override_paise: Mapped[Optional[int]] = mapped_column(Integer)
    is_oxygen_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255))

    ward: Mapped[Ward] = relationship(back_populates="beds")

    @property
    def effective_rate_paise(self) -> int:
        if self.rate_override_paise is not None:
            return self.rate_override_paise
        return self.ward.daily_rate_paise if self.ward else 0


class Admission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One inpatient stay, from admission to discharge."""

    __tablename__ = "admissions"
    __table_args__ = (
        Index("ix_admissions_status_date", "status", "admitted_at"),
        Index("ix_admissions_patient", "patient_id", "admitted_at"),
    )

    ip_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    # The OPD visit this admission came from, when it did.
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="SET NULL")
    )
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES),
        nullable=False, index=True,
    )
    admitting_doctor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    admitting_doctor_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    admission_type: Mapped[AdmissionType] = mapped_column(
        SAEnum(AdmissionType, name="admission_type", values_callable=_VALUES),
        nullable=False, default=AdmissionType.PLANNED,
    )
    status: Mapped[AdmissionStatus] = mapped_column(
        SAEnum(AdmissionStatus, name="admission_status", values_callable=_VALUES),
        nullable=False, default=AdmissionStatus.ADMITTED, index=True,
    )

    admitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    discharged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expected_stay_days: Mapped[Optional[int]] = mapped_column(Integer)

    provisional_diagnosis: Mapped[Optional[str]] = mapped_column(Text)
    final_diagnosis: Mapped[Optional[str]] = mapped_column(Text)
    reason_for_admission: Mapped[Optional[str]] = mapped_column(Text)
    # Allergies are copied onto the admission so they are on the chart at the
    # bedside without a join, and stay correct if the master record changes.
    allergies: Mapped[Optional[List[str]]] = mapped_column(JSONB, default=list)

    attendant_name: Mapped[Optional[str]] = mapped_column(String(255))
    attendant_phone: Mapped[Optional[str]] = mapped_column(String(20))
    attendant_relation: Mapped[Optional[str]] = mapped_column(String(64))

    discharge_type: Mapped[Optional[DischargeType]] = mapped_column(
        SAEnum(DischargeType, name="discharge_type", values_callable=_VALUES)
    )
    # A deposit taken at admission and set against the final bill.
    advance_paid_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Set when the patient was discharged from an earlier admission within the
    # re-admission window: a quality measure, and context for the doctor.
    readmission_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="SET NULL")
    )
    days_since_last_discharge: Mapped[Optional[int]] = mapped_column(Integer)
    final_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL")
    )

    occupancies: Mapped[List["BedOccupancy"]] = relationship(
        back_populates="admission", cascade="all, delete-orphan",
        order_by="BedOccupancy.started_at",
    )
    charges: Mapped[List["AdmissionCharge"]] = relationship(
        back_populates="admission", cascade="all, delete-orphan",
        order_by="AdmissionCharge.charged_on",
    )
    vitals: Mapped[List["VitalsRecord"]] = relationship(
        back_populates="admission", cascade="all, delete-orphan",
        order_by="VitalsRecord.recorded_at",
    )
    notes: Mapped[List["ClinicalNote"]] = relationship(
        back_populates="admission", cascade="all, delete-orphan",
        order_by="ClinicalNote.created_at",
    )
    medications: Mapped[List["MedicationOrder"]] = relationship(
        back_populates="admission", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status in (AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED)


class BedOccupancy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Which bed, from when to when.

    The row is closed rather than deleted on transfer, so the history of who
    lay where survives — which billing needs, and infection control needs more.
    """

    __tablename__ = "bed_occupancies"
    __table_args__ = (Index("ix_occupancy_bed_time", "bed_id", "started_at"),)

    admission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    bed_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("beds.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    # Denormalised so a historical charge still reads correctly after a ward
    # is renamed or a bed retired.
    bed_label: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    ward_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    daily_rate_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    transfer_reason: Mapped[Optional[str]] = mapped_column(String(255))
    moved_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    admission: Mapped[Admission] = relationship(back_populates="occupancies")


class AdmissionCharge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One posted charge against a stay.

    Bed-days are posted by the daily accrual job; procedures, investigations
    and doctor visits are posted as they happen. A unique constraint stops the
    accrual job double-posting a bed-day if it is run twice in one morning —
    which it will be, eventually.
    """

    __tablename__ = "admission_charges"
    __table_args__ = (
        UniqueConstraint(
            "admission_id", "category", "charged_on", "source_reference",
            name="uq_charge_once_per_day",
        ),
        Index("ix_charges_admission_date", "admission_id", "charged_on"),
    )

    admission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category: Mapped[ChargeCategory] = mapped_column(
        SAEnum(ChargeCategory, name="charge_category", values_callable=_VALUES),
        nullable=False,
    )
    charged_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    # Distinguishes charges that would otherwise collide on the same day:
    # the bed id for a bed-day, the order id for an investigation.
    source_reference: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    service_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_items.id", ondelete="SET NULL")
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_rate_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_billed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    posted_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    admission: Mapped[Admission] = relationship(back_populates="charges")


class VitalsRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One set of bedside observations, with the score that was acted on."""

    __tablename__ = "vitals_records"
    __table_args__ = (Index("ix_vitals_admission_time", "admission_id", "recorded_at"),)

    admission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    recorded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    recorded_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    respiratory_rate: Mapped[Optional[int]] = mapped_column(Integer)
    spo2_percent: Mapped[Optional[int]] = mapped_column(Integer)
    on_oxygen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    oxygen_litres: Mapped[Optional[float]] = mapped_column(Float)
    systolic_bp: Mapped[Optional[int]] = mapped_column(Integer)
    diastolic_bp: Mapped[Optional[int]] = mapped_column(Integer)
    pulse: Mapped[Optional[int]] = mapped_column(Integer)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float)
    consciousness: Mapped[Optional[str]] = mapped_column(String(1))  # A C V P U
    # Set for patients with a lower prescribed oxygen target (COPD).
    spo2_scale_2: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    pain_score: Mapped[Optional[int]] = mapped_column(Integer)       # 0-10
    blood_sugar_mgdl: Mapped[Optional[int]] = mapped_column(Integer)
    urine_output_ml: Mapped[Optional[int]] = mapped_column(Integer)

    # Stored, not recomputed: the number the nurse acted on at the time.
    news2_score: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    news2_risk: Mapped[Optional[str]] = mapped_column(String(16))
    news2_detail: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_note: Mapped[Optional[str]] = mapped_column(Text)

    admission: Mapped[Admission] = relationship(back_populates="vitals")


class MedicationOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A drug prescribed for the duration of the stay."""

    __tablename__ = "medication_orders"

    admission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    drug_name: Mapped[str] = mapped_column(String(255), nullable=False)
    generic_name: Mapped[Optional[str]] = mapped_column(String(255))
    strength: Mapped[Optional[str]] = mapped_column(String(64))
    dose: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    route: Mapped[MedicationRouteIPD] = mapped_column(
        SAEnum(MedicationRouteIPD, name="medication_route_ipd", values_callable=_VALUES),
        nullable=False, default=MedicationRouteIPD.ORAL,
    )
    frequency_code: Mapped[str] = mapped_column(String(16), nullable=False, default="OD")
    # The clock times a dose is due, e.g. ["08:00","20:00"]. Explicit rather
    # than derived, because a ward's drug round times are its own.
    schedule_times: Mapped[Optional[List[str]]] = mapped_column(JSONB, default=list)

    status: Mapped[MedicationStatus] = mapped_column(
        SAEnum(MedicationStatus, name="medication_status", values_callable=_VALUES),
        nullable=False, default=MedicationStatus.ACTIVE, index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[Optional[str]] = mapped_column(String(255))

    is_stat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    ordered_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    admission: Mapped[Admission] = relationship(back_populates="medications")
    administrations: Mapped[List["MedicationAdministration"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
        order_by="MedicationAdministration.due_at",
    )


class MedicationAdministration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One dose: due, and what actually happened.

    A dose not given is as clinically important as one given, so an omission
    is a row with a reason rather than a missing row.
    """

    __tablename__ = "medication_administrations"
    __table_args__ = (Index("ix_mar_due", "order_id", "due_at"),)

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medication_orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    given_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    given_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    given_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    was_given: Mapped[Optional[bool]] = mapped_column(Boolean)
    omission_reason: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    order: Mapped[MedicationOrder] = relationship(back_populates="administrations")


class ClinicalNote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Doctor rounds, nursing notes, and the discharge summary.

    Notes are append-only. A correction is a new note referring to the old
    one; editing a signed clinical entry destroys the record of what was
    believed at the time, which is the thing a note exists to preserve.
    """

    __tablename__ = "clinical_notes"
    __table_args__ = (Index("ix_notes_admission_type", "admission_id", "note_type"),)

    admission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    note_type: Mapped[NoteType] = mapped_column(
        SAEnum(NoteType, name="note_type", values_callable=_VALUES), nullable=False
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    author_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    author_role: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured SOAP fields when the note was entered that way.
    subjective: Mapped[Optional[str]] = mapped_column(Text)
    objective: Mapped[Optional[str]] = mapped_column(Text)
    assessment: Mapped[Optional[str]] = mapped_column(Text)
    plan: Mapped[Optional[str]] = mapped_column(Text)

    # True when a model drafted this. It stays visible in the record: a
    # clinician reading a note later is entitled to know what wrote it.
    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_reviewed_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    ai_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinical_notes.id", ondelete="SET NULL")
    )

    admission: Mapped[Admission] = relationship(back_populates="notes")
