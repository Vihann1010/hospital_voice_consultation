"""A patient's leave from the ward during an admission.

The patient stays admitted. `bed_retained` decides the bill: a kept bed is
held for the patient and charged as usual; a released bed goes back to the
ward, is not charged, and a bed is chosen again when the patient returns.
"""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AdmissionLeave(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "admission_leaves"

    admission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_return_on: Mapped[Optional[date]] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    bed_retained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    released_bed_label: Mapped[Optional[str]] = mapped_column(String(32))
    released_ward_name: Mapped[Optional[str]] = mapped_column(String(120))
    started_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    returned_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    return_note: Mapped[Optional[str]] = mapped_column(Text)
