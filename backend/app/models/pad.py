"""The Visit Pad: configurable clinical documents.

Every clinical screen in the old system — the OPD pad, the nursing initial
assessment, the progress note, the discharge summary, the OT note, a medical
certificate — was the same engine wearing a different layout. This is that
engine. Four tables, each holding a different kind of thing:

  PadLayout      what a document looks like: its sections, in order, and for
                 each one whether it shows on screen, whether it prints, and
                 whether it carries forward to the next visit
  PadDocument    one filled document for one patient
  PadTemplate    a saved set of values a doctor loads instead of typing
  PadCatalogue   the suggestion list that grows as staff type

`document_type` is a plain string rather than a database enum on purpose.
Part 3 adds inpatient forms, theatre notes and certificates on top of this
engine, and a Postgres enum can gain values but never lose or rename them. A
document type is configuration, and it should be as cheap to add as a row.

A signed document is never edited. A correction is a new version in the same
group, and the old one is marked superseded — the same rule inpatient notes
already follow, for the same reason: the record of what was believed at the
time is the thing a clinical document exists to preserve.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Department, PadStatus

_VALUES = lambda e: [m.value for m in e]  # noqa: E731  (see models/investigation.py)


class PadLayout(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The shape of one kind of document, for one scope.

    Scopes, from most to least specific: a doctor's own layout within a
    department, the department's layout, the hospital's layout. A document
    type nobody has configured falls back to the built-in default in
    `app/pads/defaults.py`, so a new form is usable before anyone edits it.
    """

    __tablename__ = "pad_layouts"
    __table_args__ = (
        Index("ix_pad_layouts_scope", "document_type", "department", "owner_id"),
    )

    document_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES, create_type=False)
    )
    # NULL means the layout belongs to the department or the hospital. A
    # personal layout lets one surgeon keep the order they think in without
    # imposing it on every colleague.
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sections: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Incremented on every save, and copied onto each document created from
    # it, so a document can say which revision of its layout it was made on.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class PadDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One filled clinical document."""

    __tablename__ = "pad_documents"
    __table_args__ = (
        Index("ix_pad_documents_patient_type", "patient_id", "document_type", "created_at"),
        Index("ix_pad_documents_group", "group_id", "version"),
    )

    document_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    consultation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="SET NULL"), index=True
    )
    admission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="SET NULL"), index=True
    )
    # Theatre notes belong to a surgery. They also carry the admission, when
    # there is one, so the case sheet and the records bundle find them.
    surgery_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("surgeries.id", ondelete="SET NULL"), index=True
    )
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES, create_type=False)
    )

    # The layout as it stood when this document was made. Printing a
    # two-year-old discharge summary must produce what was signed, not what
    # the layout says today after somebody reordered its sections.
    layout_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pad_layouts.id", ondelete="SET NULL")
    )
    layout_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sections: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # Section key -> that section's content. The shape depends on the kind of
    # section and is validated in `app/pads/sections.py`.
    values: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Section key -> where its first draft came from. An AI-drafted section
    # stays marked as such after a doctor edits it, because the reader of a
    # signed document is entitled to know what wrote the first version.
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[PadStatus] = mapped_column(
        SAEnum(PadStatus, name="pad_status", values_callable=_VALUES),
        nullable=False, default=PadStatus.DRAFT, index=True,
    )

    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    author_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    signed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    signed_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # --- version chain ------------------------------------------------------
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pad_documents.id", ondelete="SET NULL")
    )
    amendment_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Every print after the first is a duplicate, and says so on the page.
    print_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Certificates and consent forms only. The serial is given at first
    # signing and kept by corrections; the paper columns record that the
    # patient's signed copy of a consent form came back.
    # What signing this document issued. Filled once, when it is signed.
    prescription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="SET NULL")
    )
    investigation_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigation_orders.id", ondelete="SET NULL")
    )

    serial_number: Mapped[Optional[str]] = mapped_column(String(24), index=True)
    #: A radiology report's imaging order item.
    order_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigation_order_items.id", ondelete="SET NULL"), index=True
    )
    paper_signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paper_signed_by_name: Mapped[Optional[str]] = mapped_column(String(255))


class PadTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A saved set of section values, loaded into a document instead of typed.

    Distinct from copying the previous visit: a template is the same content
    for many patients ("post-op knee advice"), a previous visit is one
    patient's own history.
    """

    __tablename__ = "pad_templates"

    document_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES, create_type=False)
    )
    # NULL means shared with the department.
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    values: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PadCatalogueEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One phrase staff have typed before, in one category.

    The single biggest reason the old system felt fast. Nobody curates it: a
    diagnosis typed and saved becomes a suggestion the next time anyone
    starts typing in a diagnosis field, and the phrases used most rise to the
    top. A hospital's vocabulary is its own — "B/L OA knee", not the textbook
    — and this is where it accumulates.

    `department` is a plain string with "" for hospital-wide, not a nullable
    enum, because a unique constraint treats every NULL as distinct and would
    let the same phrase be stored a hundred times.
    """

    __tablename__ = "pad_catalogue"
    __table_args__ = (
        UniqueConstraint("category", "department", "normalized", name="uq_pad_catalogue_phrase"),
        Index("ix_pad_catalogue_lookup", "category", "department", "use_count"),
    )

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Lower-cased, whitespace-collapsed. "B/L OA  Knee" and "b/l oa knee" are
    # one phrase used twice, not two phrases used once.
    normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
