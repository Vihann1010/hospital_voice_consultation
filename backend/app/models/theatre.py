"""The operation theatre: rooms, the operation list, and each surgery.

A surgery is booked against a patient — usually an admission, sometimes a day
case with none — and then moves through theatre: wheeled in, anaesthetised,
operated on, closed, wheeled out. The four times between those are the legal
record of the case and the source of the surgical register, so they are stored
as columns, not buried in a note.

The operation name, surgeon and room are copied onto the surgery when it is
booked. The register printed in five years must say what was done and by whom
even if the operation list has been renamed and the surgeon has left.
"""
import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Department, SurgeryStatus

_VALUES = lambda e: [m.value for m in e]  # noqa: E731  (see models/investigation.py)


class TheatreRoom(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "theatre_rooms"

    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Operation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One entry on the hospital's operation list."""

    __tablename__ = "operations"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES, create_type=False)
    )
    grade: Mapped[Optional[str]] = mapped_column(String(16))
    default_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # The price-list code billed when a case is completed on an admission.
    # Held here rather than typed at completion, because the theatre is not
    # the place a charge should be decided.
    service_code: Mapped[Optional[str]] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Surgery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One surgical case, from booking to wheel-out."""

    __tablename__ = "surgeries"
    __table_args__ = (
        Index("ix_surgeries_room_time", "room_id", "scheduled_at"),
        Index("ix_surgeries_status_time", "status", "scheduled_at"),
    )

    ot_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    admission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="SET NULL"), index=True
    )
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES, create_type=False),
        nullable=False,
    )

    operation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operations.id", ondelete="SET NULL")
    )
    operation_name: Mapped[str] = mapped_column(String(255), nullable=False)
    laterality: Mapped[str] = mapped_column(String(24), nullable=False)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text)

    surgeon_consultant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="SET NULL")
    )
    surgeon_name: Mapped[str] = mapped_column(String(255), nullable=False)
    assistants: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    anaesthetist_name: Mapped[Optional[str]] = mapped_column(String(255))
    anaesthesia_type: Mapped[Optional[str]] = mapped_column(String(48))

    room_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theatre_rooms.id", ondelete="SET NULL")
    )
    room_name: Mapped[Optional[str]] = mapped_column(String(120))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    expected_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="elective")

    status: Mapped[SurgeryStatus] = mapped_column(
        SAEnum(SurgeryStatus, name="surgery_status", values_callable=_VALUES),
        nullable=False, default=SurgeryStatus.SCHEDULED, index=True,
    )

    wheel_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    anaesthesia_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    incision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    wheel_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    booked_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # The admission charge raised on completion, so it is never raised twice.
    charge_reference: Mapped[Optional[str]] = mapped_column(String(64))

    def times(self) -> dict:
        return {
            "wheel_in_at": self.wheel_in_at,
            "anaesthesia_start_at": self.anaesthesia_start_at,
            "incision_at": self.incision_at,
            "closure_at": self.closure_at,
            "wheel_out_at": self.wheel_out_at,
        }
