"""Booked appointments and the queue they feed.

**An appointment is not a visit.** Booking is a promise; a visit is an
attendance that has been registered and billed. Keeping them apart is what
lets the board show tomorrow's bookings without inventing visit numbers,
receipts and tokens for patients who may never arrive — and it is why
checking a patient in *converts* the appointment rather than renaming it.
The link runs one way, from the appointment to the visit it produced, so a
walk-in visit needs no appointment row at all.

**A booking does not require a patient.** Somebody rings and asks for
Tuesday morning. They may never have been here, and they may never come. If
booking demanded a UHID, the clerk would have to register a stranger to
answer the phone — filling the patient register with no-shows, and creating a
second record for the same person the next time they ring. So a booking may
instead carry the caller's name and number, and the UHID is issued at
check-in, when there is a person at the desk to register.

**Slots are computed, not stored.** The hospital does not run a fixed grid:
each consultant has their own appointment length and their own OPD hours, and
those change. Storing every empty slot as a row would mean regenerating the
day whenever a consultant's settings changed, and would go stale silently.
Instead a slot exists if it falls inside the consultant's hours and nothing
overlaps it — computed from the bookings that do exist.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AppointmentStatus, Department, Gender, VisitType

_VALUES = lambda e: [m.value for m in e]  # noqa: E731


class Appointment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        # The board is always read as "this consultant, this day", and the
        # overlap check that guards double-booking reads the same way.
        Index("ix_appointments_consultant_start", "consultant_id", "scheduled_start"),
        Index("ix_appointments_start_status", "scheduled_start", "status"),
        # One or the other, never neither. Without this a booking could exist
        # that names nobody, and it would surface as a blank row on the board
        # that no one can act on or trace back.
        CheckConstraint(
            "patient_id IS NOT NULL OR (caller_name IS NOT NULL AND caller_phone IS NOT NULL)",
            name="ck_appointment_has_someone",
        ),
    )

    # Null until the caller is registered — which is at check-in for a phone
    # booking, and at booking time for anyone already on the register.
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )

    # Who rang, when they are not (yet) a patient. Deliberately the smallest
    # set that lets the hospital call them back and recognise them at the
    # desk: everything else is asked when they are standing there, where it
    # can be got right, rather than spelled over a phone.
    caller_name: Mapped[Optional[str]] = mapped_column(String(255))
    caller_phone: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    caller_age: Mapped[Optional[int]] = mapped_column(Integer)
    caller_gender: Mapped[Optional[Gender]] = mapped_column(
        SAEnum(Gender, name="gender", values_callable=_VALUES)
    )
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Copied at booking time. The register can be edited and a consultant can
    # leave; the board still has to read correctly afterwards.
    consultant_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES), nullable=False
    )

    scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Taken from the consultant's setting at booking, not read live: changing
    # the setting must not silently resize appointments already promised.
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus, name="appointment_status", values_callable=_VALUES),
        nullable=False, default=AppointmentStatus.PENDING, index=True,
    )
    visit_type: Mapped[VisitType] = mapped_column(
        SAEnum(VisitType, name="visit_type", values_callable=_VALUES),
        nullable=False, default=VisitType.NEW,
    )

    # Set when the patient is checked in and the appointment becomes a visit.
    # Its presence is what stops the same booking being registered twice.
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="SET NULL"),
        unique=True, index=True,
    )

    reason: Mapped[Optional[str]] = mapped_column(Text)
    referred_by: Mapped[Optional[str]] = mapped_column(String(255))
    booked_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Whether the patient was reminded, so a scheduled reminder run does not
    # message the same person twice.
    reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)

