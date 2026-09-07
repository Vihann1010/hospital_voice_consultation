"""Reception, billing and finance.

Design notes worth knowing before changing anything here:

**Money is integer paise.** Never Float, never Numeric. See app/billing/money.py
for why. A Numeric column would be defensible; a Float column would silently
lose money.

**Invoice lines are denormalised.** The service name, rate and tax rate are
copied onto the line at the moment of billing rather than joined from the
tariff. A bill is a legal document: revising the tariff next month must not
retroactively change what a patient was charged in March.

**Counters are their own table.** Invoice numbers must be gapless within a
financial year, so they are allocated from a row that is locked for update,
not from `max(number) + 1`, which two cashiers billing simultaneously would
race into a duplicate.
"""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    CashSessionStatus,
    ClaimStatus,
    Department,
    InvoiceStatus,
    PayerType,
    PaymentMode,
    ServiceCategory,
    VisitStatus,
    VisitType,
)

_VALUES = lambda e: [m.value for m in e]  # noqa: E731


class DocumentCounter(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Sequential allocator for numbered documents.

    One row per (scope, period) — for example ("invoice", "26-27"). Rows are
    locked FOR UPDATE while allocating, which serialises concurrent cashiers
    and keeps the sequence gapless as GST rules require.
    """

    __tablename__ = "document_counters"
    __table_args__ = (UniqueConstraint("scope", "period", name="uq_counter_scope_period"),)

    scope: Mapped[str] = mapped_column(String(32), nullable=False)   # invoice | receipt | uhid
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # financial year, or "all"
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ServiceItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The hospital's price list.

    Rates live in the database rather than in code because the front desk
    changes them and must not need a deployment to do it.
    """

    __tablename__ = "service_items"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[ServiceCategory] = mapped_column(
        SAEnum(ServiceCategory, name="service_category", values_callable=_VALUES),
        nullable=False,
    )
    department: Mapped[Optional[Department]] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES), index=True
    )
    rate_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Most clinical services are GST-exempt; retail items are not.
    tax_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hsn_sac_code: Mapped[Optional[str]] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Visit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One attendance at the OPD.

    The administrative wrapper around a consultation: reception registers and
    bills a visit, and the clinical record (`Consultation`) attaches to it.
    A visit can exist without a consultation — a patient who paid and left —
    which is why the link is optional and lives on this side.
    """

    __tablename__ = "visits"
    __table_args__ = (
        Index("ix_visits_date_department", "visit_date", "department"),
        Index("ix_visits_patient_date", "patient_id", "visit_date"),
    )

    visit_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    consultation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="SET NULL"), index=True
    )
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES), nullable=False
    )
    doctor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    doctor_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    visit_type: Mapped[VisitType] = mapped_column(
        SAEnum(VisitType, name="visit_type", values_callable=_VALUES),
        nullable=False, default=VisitType.NEW,
    )
    status: Mapped[VisitStatus] = mapped_column(
        SAEnum(VisitStatus, name="visit_status", values_callable=_VALUES),
        nullable=False, default=VisitStatus.REGISTERED, index=True,
    )
    payer_type: Mapped[PayerType] = mapped_column(
        SAEnum(PayerType, name="payer_type", values_callable=_VALUES),
        nullable=False, default=PayerType.SELF_PAY,
    )

    visit_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Position in the day's queue for that doctor, shown on the token slip.
    token_number: Mapped[Optional[int]] = mapped_column(Integer)
    referred_by: Mapped[Optional[str]] = mapped_column(String(255))
    registered_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    invoices: Mapped[List["Invoice"]] = relationship(
        back_populates="visit", cascade="all, delete-orphan"
    )


class Invoice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_issued_status", "issued_at", "status"),
        Index("ix_invoices_patient", "patient_id", "issued_at"),
    )

    invoice_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, name="invoice_status", values_callable=_VALUES),
        nullable=False, default=InvoiceStatus.DRAFT, index=True,
    )
    payer_type: Mapped[PayerType] = mapped_column(
        SAEnum(PayerType, name="payer_type", values_callable=_VALUES),
        nullable=False, default=PayerType.SELF_PAY,
    )

    # --- amounts, all in paise -------------------------------------------
    gross_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discount_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    taxable_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cgst_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sgst_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    igst_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paid_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # What insurance is expected to cover; the balance is the patient's.
    payer_covered_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    discount_reason: Mapped[Optional[str]] = mapped_column(String(255))
    discount_approved_by: Mapped[Optional[str]] = mapped_column(String(255))

    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    visit: Mapped[Optional[Visit]] = relationship(back_populates="invoices")
    lines: Mapped[List["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan",
        order_by="InvoiceLine.position",
    )
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan",
        order_by="Payment.created_at",
    )

    @property
    def balance_paise(self) -> int:
        return self.total_paise - self.paid_paise


class InvoiceLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One charged item.

    Name, rate and tax are copied from the tariff at billing time so a later
    price revision cannot alter a bill already given to a patient.
    """

    __tablename__ = "invoice_lines"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    service_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_items.id", ondelete="SET NULL")
    )

    code: Mapped[Optional[str]] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    hsn_sac_code: Mapped[Optional[str]] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_rate_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discount_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    taxable_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Money received. Refunds are recorded as negative amounts.

    Payments are never deleted — a refund is a new row, so the audit trail of
    what was taken and what was returned stays intact.
    """

    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_received_mode", "received_at", "mode"),)

    receipt_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    cash_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cash_sessions.id", ondelete="SET NULL"), index=True
    )

    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[PaymentMode] = mapped_column(
        SAEnum(PaymentMode, name="payment_mode", values_callable=_VALUES), nullable=False
    )
    reference: Mapped[Optional[str]] = mapped_column(String(120))  # UPI ref, card last 4
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    received_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_refund: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    refund_reason: Mapped[Optional[str]] = mapped_column(Text)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class CashSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A cashier's shift.

    Reconciliation at close is the point: counted cash against expected cash,
    with any difference recorded rather than quietly absorbed.
    """

    __tablename__ = "cash_sessions"

    counter_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Reception")
    cashier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    cashier_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    status: Mapped[CashSessionStatus] = mapped_column(
        SAEnum(CashSessionStatus, name="cash_session_status", values_callable=_VALUES),
        nullable=False, default=CashSessionStatus.OPEN, index=True,
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    opening_float_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counted_cash_paise: Mapped[Optional[int]] = mapped_column(Integer)
    # Positive means more cash than expected, negative means short.
    variance_paise: Mapped[Optional[int]] = mapped_column(Integer)
    variance_note: Mapped[Optional[str]] = mapped_column(Text)


class InsurancePolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A patient's cover. One patient may hold several."""

    __tablename__ = "insurance_policies"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    payer_type: Mapped[PayerType] = mapped_column(
        SAEnum(PayerType, name="payer_type", values_callable=_VALUES),
        nullable=False, default=PayerType.INSURANCE,
    )
    insurer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tpa_name: Mapped[Optional[str]] = mapped_column(String(255))
    policy_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    member_id: Mapped[Optional[str]] = mapped_column(String(64))
    scheme_name: Mapped[Optional[str]] = mapped_column(String(255))  # Ayushman Bharat etc.

    valid_from: Mapped[Optional[date]] = mapped_column(Date)
    valid_to: Mapped[Optional[date]] = mapped_column(Date)
    sum_insured_paise: Mapped[Optional[int]] = mapped_column(Integer)
    balance_paise: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    card_file: Mapped[Optional[str]] = mapped_column(String(512))


class InsuranceClaim(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A cashless request against a policy.

    Deliberately transport-agnostic. Every TPA has its own portal, form and
    (sometimes) API, so this records the state of a claim and the documents
    attached to it; how it is actually transmitted is per-payer and belongs
    outside the model.
    """

    __tablename__ = "insurance_claims"

    claim_number: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insurance_policies.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="SET NULL"), index=True
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True
    )

    status: Mapped[ClaimStatus] = mapped_column(
        SAEnum(ClaimStatus, name="claim_status", values_callable=_VALUES),
        nullable=False, default=ClaimStatus.DRAFT, index=True,
    )
    # The payer's own reference, once they issue one.
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), index=True)

    claimed_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settled_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # What the patient pays regardless: deductible, co-pay, non-covered items.
    patient_liability_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    diagnosis: Mapped[Optional[str]] = mapped_column(Text)
    treatment_summary: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    query_detail: Mapped[Optional[str]] = mapped_column(Text)

    # Every state change, appended — who did what and when.
    history: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, default=list)
    documents: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, default=list)
