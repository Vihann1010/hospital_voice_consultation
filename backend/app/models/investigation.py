"""Investigation ordering, report storage and version history.

All tables here are new, so `Base.metadata.create_all` provisions them without
touching the Phase 1 schema.

Version history model: every upload belongs to a `group_id`. A corrected or
re-issued report is uploaded against the previous report, inherits its
`group_id`, takes `version + 1`, and marks the predecessor SUPERSEDED. The
current report for a group is simply the highest version that is not
superseded, so nothing is ever destroyed or overwritten.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

# Every Python enum below is a str-Enum whose .name (e.g. "ORTHOPEDICS") differs
# from its .value (e.g. "orthopedics"). SQLAlchemy binds .name by default unless
# told otherwise, which does not match the Postgres types created from the
# lowercase .value strings elsewhere in the schema. values_callable fixes the
# binding; name= must match the type already created by that first usage.
_VALUES = lambda e: [m.value for m in e]  # noqa: E731
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    Department,
    DocumentKind,
    InvestigationCategory,
    InvestigationPriority,
    OrderStatus,
    ReportStatus,
)


class InvestigationOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A request slip: one or more investigations ordered at one moment."""

    __tablename__ = "investigation_orders"

    consultation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="SET NULL"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ordered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    ordered_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES), nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", values_callable=_VALUES),
        nullable=False, default=OrderStatus.ISSUED, index=True,
    )
    priority: Mapped[InvestigationPriority] = mapped_column(
        SAEnum(InvestigationPriority, name="investigation_priority", values_callable=_VALUES),
        nullable=False, default=InvestigationPriority.ROUTINE,
    )
    clinical_notes: Mapped[Optional[str]] = mapped_column(Text)
    provisional_diagnosis: Mapped[Optional[str]] = mapped_column(Text)
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    items: Mapped[List["InvestigationOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="InvestigationOrderItem.position"
    )
    reports: Mapped[List["InvestigationReport"]] = relationship(back_populates="order")


class InvestigationOrderItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One investigation on a request slip.

    The catalog lives in code (app/investigations/catalog.py), so the name and
    category are denormalised here: a slip printed in 2026 must still read
    correctly if the catalog is revised later.
    """

    __tablename__ = "investigation_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigation_orders.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[InvestigationCategory] = mapped_column(
        SAEnum(InvestigationCategory, name="investigation_category", values_callable=_VALUES),
        nullable=False,
    )
    specimen_or_site: Mapped[Optional[str]] = mapped_column(String(255))
    preparation: Mapped[Optional[str]] = mapped_column(Text)
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    order: Mapped[InvestigationOrder] = relationship(back_populates="items")


class InvestigationReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An uploaded report file plus everything derived from it."""

    __tablename__ = "investigation_reports"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    consultation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="SET NULL"), index=True
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigation_orders.id", ondelete="SET NULL"), index=True
    )

    # --- version chain ---
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replaces_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigation_reports.id", ondelete="SET NULL")
    )
    revision_note: Mapped[Optional[str]] = mapped_column(Text)

    # --- file ---
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Report")
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # --- what kind of document this is -------------------------------------
    # Declared by whoever uploaded it. NULL means nobody said, which is not
    # the same as "other": an undeclared document is classified from its text
    # and treated cautiously, where a declared one is checked against that
    # classification and refused analysis when the two disagree.
    document_kind: Mapped[Optional[DocumentKind]] = mapped_column(
        SAEnum(DocumentKind, name="document_kind", values_callable=_VALUES), index=True
    )

    # --- derived ---
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, name="report_status", values_callable=_VALUES),
        nullable=False, default=ReportStatus.UPLOADED, index=True,
    )
    extraction_method: Mapped[Optional[str]] = mapped_column(String(64))
    extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    error_detail: Mapped[Optional[str]] = mapped_column(Text)

    uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    order: Mapped[Optional[InvestigationOrder]] = relationship(back_populates="reports")


class DoctorFavoriteInvestigation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A clinician's starred investigations, for one-tap ordering."""

    __tablename__ = "doctor_favorite_investigations"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_favorite_user_code"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)


class InvestigationTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A saved set of investigations.

    `user_id` NULL means the template is shared with the whole department.
    """

    __tablename__ = "investigation_templates"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    codes: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
