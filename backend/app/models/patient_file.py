"""Files kept on a patient's record: ID proofs, referral letters, old records,
signed consent scans, clinical photographs.

Unlike an investigation report, nothing is read out of these files; they are
stored, categorised and bound into the records bundle. They are never deleted.
A file attached in error is withdrawn with a reason, hidden from everyday
lists, and kept.
"""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PatientFileCategory


class PatientFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "patient_files"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    consultation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="SET NULL")
    )
    admission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="SET NULL")
    )
    #: A signed consent scan belongs to the consent form it is the paper copy of.
    pad_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pad_documents.id", ondelete="SET NULL")
    )
    category: Mapped[PatientFileCategory] = mapped_column(
        Enum(PatientFileCategory, name="patient_file_category",
             values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    withdrawn_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    withdraw_reason: Mapped[Optional[str]] = mapped_column(Text)
