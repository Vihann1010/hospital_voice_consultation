"""Prescriptions and outbound message delivery.

New tables only, so `create_all` provisions them without touching the existing
schema. Medicines are denormalised onto their own rows rather than stored as
JSON because they are queried (repeat prescriptions, drug usage) and because a
prescription is a legal record: the exact text issued must survive any later
change to the formulary.
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
)

_VALUES = lambda e: [m.value for m in e]  # noqa: E731  (see models/investigation.py)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    DeliveryChannel,
    DeliveryStatus,
    Department,
    PrescriptionStatus,
)


class Prescription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "prescriptions"

    # Human-readable identifier printed on the sheet and encoded in the QR.
    prescription_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    consultation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="SET NULL"), index=True
    )
    doctor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    doctor_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    doctor_qualification: Mapped[Optional[str]] = mapped_column(String(255))
    doctor_registration: Mapped[Optional[str]] = mapped_column(String(120))
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES), nullable=False
    )

    status: Mapped[PrescriptionStatus] = mapped_column(
        SAEnum(PrescriptionStatus, name="prescription_status", values_callable=_VALUES),
        nullable=False, default=PrescriptionStatus.DRAFT, index=True,
    )

    # Clinical content
    diagnosis: Mapped[Optional[str]] = mapped_column(Text)
    cause: Mapped[Optional[str]] = mapped_column(Text)
    chief_complaint: Mapped[Optional[str]] = mapped_column(Text)
    clinical_findings: Mapped[Optional[str]] = mapped_column(Text)
    investigations_advised: Mapped[Optional[List[str]]] = mapped_column(JSONB, default=list)
    general_instructions: Mapped[Optional[str]] = mapped_column(Text)
    follow_up_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    follow_up_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Provenance and safety
    dictation_transcript: Mapped[Optional[str]] = mapped_column(Text)
    acknowledged_alerts: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, default=list)

    # Output
    pdf_filename: Mapped[Optional[str]] = mapped_column(String(512))
    pdf_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    medicines: Mapped[List["PrescriptionMedicine"]] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
        order_by="PrescriptionMedicine.position",
    )
    deliveries: Mapped[List["MessageDelivery"]] = relationship(
        back_populates="prescription", order_by="MessageDelivery.created_at"
    )


class PrescriptionMedicine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "prescription_medicines"

    prescription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    formulary_code: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    generic: Mapped[Optional[str]] = mapped_column(String(255))
    form: Mapped[Optional[str]] = mapped_column(String(64))
    strength: Mapped[Optional[str]] = mapped_column(String(64))
    dosage: Mapped[Optional[str]] = mapped_column(String(120))
    frequency_code: Mapped[Optional[str]] = mapped_column(String(32))
    frequency_text: Mapped[Optional[str]] = mapped_column(String(120))
    duration: Mapped[Optional[str]] = mapped_column(String(120))
    timing: Mapped[Optional[str]] = mapped_column(String(120))
    route: Mapped[Optional[str]] = mapped_column(String(64))
    instructions: Mapped[Optional[str]] = mapped_column(Text)

    # "dictated" | "manual" | "catalog" — useful for measuring dictation quality.
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")

    prescription: Mapped[Prescription] = relationship(back_populates="medicines")


class MessageDelivery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Outbound delivery attempt for a document.

    Deliberately generic (`entity_type` / `entity_id`) so reports and other
    documents can reuse the same tracking and retry machinery, with a typed
    relationship to prescriptions for the common case.
    """

    __tablename__ = "message_deliveries"

    entity_type: Mapped[str] = mapped_column(String(48), nullable=False, default="prescription")
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    prescription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True
    )

    channel: Mapped[DeliveryChannel] = mapped_column(
        SAEnum(DeliveryChannel, name="delivery_channel", values_callable=_VALUES),
        nullable=False, default=DeliveryChannel.WHATSAPP,
    )
    provider: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    recipient: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus, name="delivery_status", values_callable=_VALUES),
        nullable=False, default=DeliveryStatus.PENDING, index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    history: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, default=list)

    requested_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    prescription: Mapped[Optional[Prescription]] = relationship(back_populates="deliveries")
