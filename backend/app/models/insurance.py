"""Money a TPA or insurer sent against a claim.

Recorded apart from the claim because payers settle in parts — an interim
payment, then the balance after a query, sometimes a TDS certificate months
later — and each part reaches the bank on its own day. A settlement is never
edited; a wrong one is cancelled with a reason and entered again, and the books
reverse it the same way.
"""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ClaimSettlement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_settlements"
    __table_args__ = (
        CheckConstraint(
            "received_paise >= 0 AND tds_paise >= 0 AND deduction_paise >= 0 "
            "AND received_paise + tds_paise + deduction_paise > 0",
            name="ck_claim_settlement_amounts",
        ),
    )

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insurance_claims.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    received_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # What reached the bank.
    received_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Tax the payer deducted at source. The hospital claims it back against its
    # own tax, so it is an asset, not a loss.
    tds_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # What the payer refused to pay: room rent over the limit, non-payable
    # consumables. Written off unless the hospital bills the family for it.
    deduction_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deduction_reason: Mapped[Optional[str]] = mapped_column(Text)
    # net_banking | cheque | upi
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_by_name: Mapped[Optional[str]] = mapped_column(String(255))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
