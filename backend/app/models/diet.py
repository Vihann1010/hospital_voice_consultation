"""Diets the kitchen prepares, and each admitted patient's diet over their stay.

A diet order is date-stamped rather than a field on the admission, because a
patient's diet changes during a stay — nil by mouth before theatre, liquids
after, soft the next day — and the kitchen needs to know what was in effect at
each meal, not only what is true now. Placing a new order closes the previous
one at the new order's start; nothing is overwritten.

The diet's name is copied onto the order, so a sheet reprinted after the list
has been renamed still says what was actually served.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DietMode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "diet_modes"

    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Nothing goes to the bed. Shown to the kitchen as such, not as a diet.
    is_nil_by_mouth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DietOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "diet_orders"
    __table_args__ = (Index("ix_diet_orders_admission_start", "admission_id", "starts_at"),)

    admission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("diet_modes.id", ondelete="SET NULL")
    )
    mode_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_nil_by_mouth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ordered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    ordered_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ended_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    end_reason: Mapped[Optional[str]] = mapped_column(Text)
