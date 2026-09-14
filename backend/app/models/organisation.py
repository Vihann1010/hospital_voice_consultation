"""Organisations the hospital has negotiated a price list with.

An employer, a TPA, an insurer, a government scheme. What they have in common
is the only thing this table cares about: they have agreed rates that differ
from the counter's, and a patient who arrives under one of them must be
charged the agreed figure without the clerk having to remember it.

**Kept separate from the insurance policy.** A policy records one patient's
cover; this records a commercial relationship with the hospital. The same
employer covers hundreds of patients under one rate card, and storing the
insurer's name as free text on each policy — as the previous shape did —
makes "what did we agree with them" unanswerable, and misspellings invisible.

**Rates are per service, not a blanket discount.** A discount percentage is
offered as a fallback because some agreements really are "ten percent off
everything", but the common case is a negotiated figure for the twenty
procedures that organisation's patients actually use, and averaging those
into a percentage loses the agreement.
"""
import uuid
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PayerType

_VALUES = lambda e: [m.value for m in e]  # noqa: E731


class Organisation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organisations"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payer_type: Mapped[PayerType] = mapped_column(
        SAEnum(PayerType, name="payer_type", values_callable=_VALUES),
        nullable=False, default=PayerType.CORPORATE,
    )

    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone_number: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(Text)

    # Applied to any service with no negotiated rate of its own. Whole
    # percent: an agreement expressed in fractions of a percent is not an
    # agreement anybody at a counter can check.
    default_discount_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # How long the hospital waits to be paid. Not enforced here; the
    # outstanding report reads it to age a debt.
    credit_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    rates: Mapped[List["NegotiatedRate"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )


class NegotiatedRate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """What one organisation pays for one service.

    Stored as an absolute figure rather than a discount off the tariff. When
    the hospital raises its own prices next year, an agreed rate must not
    quietly rise with them — that is the whole point of having agreed it.
    """

    __tablename__ = "negotiated_rates"
    __table_args__ = (
        UniqueConstraint(
            "organisation_id", "service_item_id", name="uq_rate_org_service"
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    service_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    rate_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    organisation: Mapped[Organisation] = relationship(back_populates="rates")
