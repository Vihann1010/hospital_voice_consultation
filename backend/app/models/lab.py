"""The in-house laboratory.

**Masters.** A lab test is a price code and a list of parameters; each
parameter carries its unit, method, and the reference ranges this laboratory's
pathologist has set. Ranges are data, not code, because they follow the
analyser and the reagent kit, and change when either does. A test whose ranges
have been edited is not reviewed again until the pathologist says so, and an
unreviewed test cannot be verified.

**Requests.** Registering tests for a patient creates a request with its own
LAB number and one item per test. Each item stores its results as a snapshot —
name, unit, method, value, flag and the reference range that was printed — so a
report printed next year reads exactly as it did the day it was verified, even
after the masters have moved on.

**Corrections.** A verified result is never edited. It is reopened with a
reason; the verified version is kept in `amendments`, the version number goes
up, and the report prints as amended once it is verified again.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
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


class LabMaster(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Short lists the lab picks from: units, methods, specimens, antibiotics,
    organisms and the report groups (Haematology, Biochemistry...)."""

    __tablename__ = "lab_masters"
    __table_args__ = (UniqueConstraint("kind", "name", name="uq_lab_master_kind_name"),)

    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(32))
    # An antibiotic's class, so the sensitivity table can be read by class.
    category: Mapped[Optional[str]] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LabTest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "lab_tests"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    group_name: Mapped[str] = mapped_column(String(64), nullable=False, default="General")
    specimen: Mapped[Optional[str]] = mapped_column(String(120))
    # The price-list code billed when the test is registered.
    service_code: Mapped[Optional[str]] = mapped_column(String(32))
    # The investigation catalogue code a doctor orders, so an order finds its test.
    catalog_code: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    is_culture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    turnaround_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    # Printed under the results: method notes, interpretation bands.
    interpretation: Mapped[Optional[str]] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ranges_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ranges_reviewed_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    parameters: Mapped[List["LabParameter"]] = relationship(
        back_populates="test", cascade="all, delete-orphan", order_by="LabParameter.position"
    )


class LabParameter(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One line of a test's result: haemoglobin within a CBC."""

    __tablename__ = "lab_parameters"

    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # The reference-range key used when reading an analyser printout.
    analyte_key: Mapped[Optional[str]] = mapped_column(String(64))
    aliases: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    result_type: Mapped[str] = mapped_column(String(16), nullable=False, default="numeric")
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    method: Mapped[Optional[str]] = mapped_column(String(120))
    choices: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    normal_values: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    # [{sex, min_age, max_age, low, high, critical_low, critical_high}]
    ranges: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Printed instead of the computed range when set, e.g. "Desirable < 200".
    range_text: Mapped[Optional[str]] = mapped_column(String(255))
    print_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    test: Mapped[LabTest] = relationship(back_populates="parameters")


class LabRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "lab_requests"
    __table_args__ = (Index("ix_lab_requests_status_created", "status", "created_at"),)

    lab_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    admission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="SET NULL"), index=True
    )
    consultation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="SET NULL")
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigation_orders.id", ondelete="SET NULL"), index=True
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True
    )
    # invoice | ipd | unbilled
    billing: Mapped[str] = mapped_column(String(16), nullable=False, default="invoice")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="registered")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="routine")
    referred_by: Mapped[Optional[str]] = mapped_column(String(255))
    consultant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="SET NULL")
    )
    clinical_notes: Mapped[Optional[str]] = mapped_column(Text)
    registered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    registered_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sample_collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sample_collected_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    cancelled_by_name: Mapped[Optional[str]] = mapped_column(String(255))

    items: Mapped[List["LabRequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="LabRequestItem.position"
    )


class LabRequestItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "lab_request_items"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_tests.id", ondelete="SET NULL"), index=True
    )
    order_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigation_order_items.id", ondelete="SET NULL"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_name: Mapped[str] = mapped_column(String(64), nullable=False, default="General")
    specimen: Mapped[Optional[str]] = mapped_column(String(120))
    is_culture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unit_rate_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The admission charge raised for this test, when billed to the stay.
    charge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admission_charges.id", ondelete="SET NULL")
    )
    # registered | collected | entered | verified | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="registered", index=True)
    results: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    culture: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    remarks: Mapped[Optional[str]] = mapped_column(Text)
    # Who was told about a critical value, and when — required to verify one.
    critical_note: Mapped[Optional[str]] = mapped_column(Text)
    entered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    entered_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    verified_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    verifier_qualification: Mapped[Optional[str]] = mapped_column(String(255))
    verifier_registration: Mapped[Optional[str]] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    amendments: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    cancelled_by_name: Mapped[Optional[str]] = mapped_column(String(255))

    request: Mapped[LabRequest] = relationship(back_populates="items")
