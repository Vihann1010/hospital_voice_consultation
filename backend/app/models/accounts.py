"""The books: account groups, ledgers, vouchers and consultant payouts.

**Vouchers are never edited.** A voucher that turns out wrong is reversed by a
second voucher with its lines swapped, and the original stays readable. For
vouchers posted from counter records the engine does this itself when the
record changes; a manual voucher is reversed by the accountant.

**One live voucher per source record.** A bill, receipt or advance has at most
one posted, unreversed voucher at a time, enforced by a partial unique index,
so running the posting engine twice cannot post anything twice.

**Balances are derived.** A ledger's balance is its opening balance plus the
sum of its voucher lines; reversed vouchers and their reversals both count,
and cancel each other out.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AccountGroup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "account_groups"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    # asset | liability | equity | income | expense
    nature: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_groups.id", ondelete="RESTRICT")
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Ledger(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ledgers"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_groups.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # The posting engine's name for this ledger. Unique; null for ledgers the
    # accountant adds.
    system_key: Mapped[Optional[str]] = mapped_column(String(48), unique=True)
    consultant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="RESTRICT"), unique=True
    )
    # Signed: a debit balance is positive, a credit balance negative.
    opening_balance_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Voucher(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vouchers"
    __table_args__ = (
        Index("ix_vouchers_date_type", "voucher_date", "voucher_type"),
        Index("ix_vouchers_source", "source_type", "source_id"),
    )

    voucher_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    # sales | receipt | payment | journal | contra
    voucher_type: Mapped[str] = mapped_column(String(16), nullable=False)
    financial_year: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    narration: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # invoice | payment | wallet_entry | legacy_advance | payout | payout_payment | manual
    source_type: Mapped[Optional[str]] = mapped_column(String(32))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # posted | reversed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="posted")
    reversal_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vouchers.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reversed_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    reversal_reason: Mapped[Optional[str]] = mapped_column(Text)
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL")
    )
    consultant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="SET NULL")
    )
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    lines: Mapped[List["VoucherLine"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan", order_by="VoucherLine.position"
    )


class VoucherLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "voucher_lines"
    __table_args__ = (
        CheckConstraint("debit_paise >= 0 AND credit_paise >= 0", name="ck_voucher_line_positive"),
        CheckConstraint("(debit_paise = 0) <> (credit_paise = 0)", name="ck_voucher_line_one_side"),
        Index("ix_voucher_lines_ledger", "ledger_id"),
    )

    voucher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vouchers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ledger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledgers.id", ondelete="RESTRICT"), nullable=False
    )
    debit_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    narration: Mapped[Optional[str]] = mapped_column(Text)

    voucher: Mapped[Voucher] = relationship(back_populates="lines")


class ConsultantPayout(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One payout run for one consultant and period.

    Approving it locks the bills it counted and posts the fee as owed; paying
    it posts the payment. A payout can be cancelled only before it is paid,
    which unlocks the bills and reverses the fee.
    """

    __tablename__ = "consultant_payouts"

    payout_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    consultant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    consultant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    share_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    categories: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    base_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tds_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_paid_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # approved | paid | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="approved", index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_on: Mapped[Optional[date]] = mapped_column(Date)
    paid_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    payment_mode: Mapped[Optional[str]] = mapped_column(String(16))
    payment_reference: Mapped[Optional[str]] = mapped_column(String(120))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    accrual_voucher_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vouchers.id", ondelete="RESTRICT")
    )
    payment_voucher_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vouchers.id", ondelete="RESTRICT")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    items: Mapped[List["ConsultantPayoutItem"]] = relationship(
        back_populates="payout", cascade="all, delete-orphan", order_by="ConsultantPayoutItem.position"
    )


class ConsultantPayoutItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "consultant_payout_items"

    payout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultant_payouts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # bill | refund
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="bill")
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), index=True
    )
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    patient_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    eligible_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    payout: Mapped[ConsultantPayout] = relationship(back_populates="items")
