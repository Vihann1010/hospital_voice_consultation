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
    CheckConstraint,
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
    WalletEntryKind,
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

    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)

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

    # Whose work this bill is for. Copied onto the invoice rather than
    # reached through the visit, because a bill can be raised at the counter
    # with no visit at all — and when it is, the consultant's free-follow-up
    # and first-consultation rules would otherwise never fire, silently.
    # Part 5's consultant payout and consultant-wise billing reports need the
    # same attribution.
    consultant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="SET NULL"), index=True
    )
    doctor_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # The agreement this bill was priced under, when it was not the counter's
    # own tariff.
    organisation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="SET NULL"),
        index=True,
    )
    # Why: "Free follow-up - seen 4 Sept", "Acme Ltd agreed rate". Stored on
    # the bill rather than recomputed, because the consultant's window and
    # the rate card both change, and a bill has to keep explaining itself
    # after they do.
    pricing_notes: Mapped[Optional[List[str]]] = mapped_column(JSONB)

    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Corrections to a bill nobody has paid yet. Counted and dated so that a
    # bill amended three times before the patient paid is visible as such;
    # the alternative is a document that quietly differs from the one the
    # patient was shown ten minutes ago.
    amended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    amendment_reason: Mapped[Optional[str]] = mapped_column(Text)
    amendment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Set by the consultant payout run once this invoice has been counted
    # into somebody's settled share. After that nothing about it may move —
    # cancelling it would silently change a payment already made to a doctor.
    # Nothing sets this yet; the payout run arrives in Part 5. The guard
    # exists now so that every correction path is already written to respect
    # it, rather than each one having to be found and patched later.
    payout_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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
    # What the mode itself requires: a cheque number and bank, a card's last
    # four digits, a UPI transaction id. One JSON column rather than a dozen
    # mostly-null ones, because the set differs per mode and grows whenever
    # the hospital accepts a new instrument. The shape is enforced in
    # app/billing/payment_modes.py, not here.
    mode_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    received_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_refund: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    refund_reason: Mapped[Optional[str]] = mapped_column(Text)

    # A cancelled receipt is not a refund, and conflating the two is a real
    # accounting error. A refund means money went back to the patient. A
    # cancellation means the receipt should never have existed — the wrong
    # amount, the wrong mode, the wrong patient — and no money moved at all.
    # The row is kept and marked rather than deleted, because a receipt
    # number handed to a patient has to remain explicable.
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)
    cancelled_by_name: Mapped[Optional[str]] = mapped_column(String(255))

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class PatientWallet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A patient's running credit with the hospital.

    Two things make this a table rather than a sum over the entries.

    **It is locked.** Spending from a wallet is read-balance-then-write, and
    two counters doing that at once would both see the same rupees and both
    spend them. The balance row is taken FOR UPDATE for the duration, which
    is what makes the negative-balance guard a guarantee rather than a
    hopeful check.

    **It is reconcilable.** The entries are the ledger and this is the
    balance; if they ever disagree, that disagreement is itself the alarm.
    Deriving the balance on every read would hide the bug instead.
    """

    __tablename__ = "patient_wallets"
    __table_args__ = (
        # A balance that can go negative is a loan, and this hospital does
        # not make loans through the wallet.
        CheckConstraint("balance_paise >= 0", name="ck_wallet_not_negative"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    balance_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    entries: Mapped[List["WalletEntry"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan",
        order_by="WalletEntry.created_at",
    )


class WalletEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One movement in or out of a patient's credit.

    Append-only. A correction is another entry, never an edit — the patient
    is told a balance at the counter, and the only way to explain how it got
    there is a line for every movement.

    `balance_after_paise` is stored rather than recomputed so a statement
    printed today still reads correctly after an older entry is discovered
    and appended out of order.
    """

    __tablename__ = "wallet_entries"
    __table_args__ = (
        Index("ix_wallet_entries_patient_time", "patient_id", "created_at"),
    )

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient_wallets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    kind: Mapped[WalletEntryKind] = mapped_column(
        SAEnum(WalletEntryKind, name="wallet_entry_kind", values_callable=_VALUES),
        nullable=False, index=True,
    )
    # Signed: positive puts money on account, negative takes it off.
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after_paise: Mapped[int] = mapped_column(Integer, nullable=False)

    # How the money came or went, for deposits and withdrawals. The drawer
    # holds only the cash ones; a UPI advance is never in it.
    mode: Mapped[Optional[PaymentMode]] = mapped_column(
        SAEnum(PaymentMode, name="payment_mode", values_callable=_VALUES, create_type=False)
    )
    # The stay an advance was taken for, so it is set against that stay's bill.
    admission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="SET NULL"), index=True
    )
    # What the movement was for, when it involved a bill or a receipt.
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True
    )
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL")
    )
    receipt_number: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    wallet: Mapped[PatientWallet] = relationship(back_populates="entries")


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
    # The TPA or insurer in the organisation register, when it is there. The
    # names above stay as typed from the card, which is what the payer quotes.
    organisation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="SET NULL"), index=True
    )


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

    # Who pays: the organisation the policy names, and its name as it stood
    # when the claim was opened.
    organisation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="SET NULL"), index=True
    )
    payer_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    admission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admissions.id", ondelete="SET NULL"), index=True
    )

    # Cashless: what was asked for before treatment and what the payer allowed.
    pre_auth_requested_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pre_auth_approved_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The payer's share put on the hospital bill, as an insurance payment. The
    # family owes the rest.
    booked_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    booking_payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL")
    )
    # Received plus TDS, from live settlements. Kept in step by the claim service.
    settled_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
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
