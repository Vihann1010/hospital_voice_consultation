"""API contracts for reception, billing and finance.

Amounts cross the wire in **paise** as integers, matching storage exactly. A
rupee float in JSON would reintroduce the precision problem the whole billing
layer exists to avoid, so conversion for display happens in the interface.
"""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    WalletEntryKind,
    CashSessionStatus,
    ClaimStatus,
    Department,
    Gender,
    InvoiceStatus,
    PayerType,
    PaymentMode,
    ServiceCategory,
    VisitStatus,
    VisitType,
)


# ------------------------------------------------------------------ patients
class PatientRegisterRequest(BaseModel):
    """What the counter may record about a patient.

    Only four fields are required here, and that is deliberate: which of the
    rest the counter must fill in is the hospital's decision, held in
    patient_field_settings and enforced by the form. Making them mandatory in
    the API as well would mean a settings change needed a deployment.

    Unknown fields are refused rather than ignored. Pydantic's default is to
    drop them silently, which means a form sending a field this schema has not
    caught up with would appear to save and simply lose the data.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    age: int = Field(ge=0, le=120)
    gender: Gender
    phone_number: str = Field(min_length=6, max_length=20)

    date_of_birth: Optional[date] = None
    address: Optional[str] = Field(default=None, max_length=512)
    city: Optional[str] = Field(default=None, max_length=120)
    blood_group: Optional[str] = Field(default=None, max_length=8)
    emergency_contact_name: Optional[str] = Field(default=None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(default=None, max_length=20)

    title: Optional[str] = Field(default=None, max_length=16)
    guardian_relation: Optional[str] = Field(default=None, max_length=16)
    guardian_name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    govt_id_type: Optional[str] = Field(default=None, max_length=32)
    govt_id_number: Optional[str] = Field(default=None, max_length=64)
    state: Optional[str] = Field(default=None, max_length=120)
    country: Optional[str] = Field(default=None, max_length=120)
    pincode: Optional[str] = Field(default=None, max_length=12)
    religion: Optional[str] = Field(default=None, max_length=64)
    marital_status: Optional[str] = Field(default=None, max_length=32)
    nationality: Optional[str] = Field(default=None, max_length=64)
    occupation: Optional[str] = Field(default=None, max_length=120)
    category: Optional[str] = Field(default=None, max_length=64)
    group_one: Optional[str] = Field(default=None, max_length=64)
    group_two: Optional[str] = Field(default=None, max_length=64)


class PatientCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    uhid: Optional[str] = None
    name: str
    age: int
    gender: Gender
    phone_number: str
    city: Optional[str] = None
    blood_group: Optional[str] = None
    created_at: datetime


# -------------------------------------------------------------------- visits
class VisitOpenRequest(BaseModel):
    patient_id: uuid.UUID
    department: Department
    doctor_id: Optional[uuid.UUID] = None
    doctor_name: str = ""
    visit_type: VisitType = VisitType.NEW
    payer_type: PayerType = PayerType.SELF_PAY
    referred_by: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None


class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    visit_number: str
    patient_id: uuid.UUID
    patient_name: str = ""
    consultation_id: Optional[uuid.UUID] = None
    department: Department
    doctor_name: str
    visit_type: VisitType
    status: VisitStatus
    payer_type: PayerType
    visit_date: date
    token_number: Optional[int] = None
    referred_by: Optional[str] = None
    registered_by_name: str = ""
    created_at: datetime


# ------------------------------------------------------------------- tariff
class ServiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    category: ServiceCategory
    department: Optional[Department] = None
    rate_paise: int
    tax_percent: int
    hsn_sac_code: Optional[str] = None
    is_active: bool


class ServiceItemUpsert(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    category: ServiceCategory
    department: Optional[Department] = None
    rate_paise: int = Field(ge=0)
    tax_percent: int = Field(default=0, ge=0, le=28)
    hsn_sac_code: Optional[str] = Field(default=None, max_length=16)
    is_active: bool = True


# ------------------------------------------------------------------ billing
class InvoiceItemRequest(BaseModel):
    service_item_id: Optional[uuid.UUID] = None
    code: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = Field(default=None, max_length=255)
    quantity: int = Field(default=1, ge=1, le=999)
    unit_rate_paise: Optional[int] = Field(default=None, ge=0)
    tax_percent: Optional[int] = Field(default=None, ge=0, le=28)
    discount_paise: int = Field(default=0, ge=0)


class DiaryEntryOut(BaseModel):
    """One dated movement in a patient's history, whatever kind it was."""

    kind: str
    reference: str
    date: date
    description: str
    gross_paise: int
    discount_paise: int
    net_paise: int
    received_paise: int
    refunded_paise: int
    balance_paise: int
    running_balance_paise: int
    status: str
    cancelled: bool
    credited_to_ipd: bool
    invoice_id: Optional[uuid.UUID] = None
    visit_id: Optional[uuid.UUID] = None
    admission_id: Optional[uuid.UUID] = None
    notes: List[str] = []


class DiaryPatientOut(BaseModel):
    id: uuid.UUID
    uhid: Optional[str] = None
    name: str
    age: int
    gender: str
    phone_number: str


class DiaryTotalsOut(BaseModel):
    gross_paise: int
    discount_paise: int
    net_paise: int
    received_paise: int
    refunded_paise: int
    outstanding_paise: int
    #: Reported beside what is owed, never netted off it.
    wallet_balance_paise: int
    visit_count: int
    admission_count: int


class PatientDiaryOut(BaseModel):
    patient: DiaryPatientOut
    totals: DiaryTotalsOut
    entries: List[DiaryEntryOut] = []


class QuoteRequest(BaseModel):
    """Price a bill without raising it."""

    model_config = ConfigDict(extra="forbid")

    patient_id: Optional[uuid.UUID] = None
    consultant_id: Optional[uuid.UUID] = None
    doctor_name: Optional[str] = None
    organisation_id: Optional[uuid.UUID] = None
    items: List[InvoiceItemRequest] = Field(min_length=1)
    invoice_discount_paise: int = Field(default=0, ge=0)


class QuoteLineOut(BaseModel):
    description: str
    code: Optional[str] = None
    quantity: int
    unit_rate_paise: int
    total_paise: int


class QuoteOut(BaseModel):
    gross_paise: int
    discount_paise: int
    taxable_paise: int
    tax_paise: int
    total_paise: int
    #: Why a line came out as it did, in the clerk's language.
    notes: List[str] = []
    lines: List[QuoteLineOut] = []


class InvoiceCreateRequest(BaseModel):
    # Who is being seen and under whose agreement. Both optional: a bill for
    # a dressing has no consultant, and most patients pay for themselves.
    # When given, the consultant's free-follow-up window and the
    # organisation's rate card are applied without the counter restating them.
    consultant_id: Optional[uuid.UUID] = None
    doctor_name: Optional[str] = None
    organisation_id: Optional[uuid.UUID] = None
    patient_id: uuid.UUID
    visit_id: Optional[uuid.UUID] = None
    items: List[InvoiceItemRequest] = Field(min_length=1)
    invoice_discount_paise: int = Field(default=0, ge=0)
    discount_reason: Optional[str] = Field(default=None, max_length=255)
    payer_type: PayerType = PayerType.SELF_PAY
    payer_covered_paise: int = Field(default=0, ge=0)
    issue: bool = True


class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    code: Optional[str] = None
    description: str
    hsn_sac_code: Optional[str] = None
    quantity: int
    unit_rate_paise: int
    discount_paise: int
    tax_percent: int
    taxable_paise: int
    tax_paise: int
    total_paise: int


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    receipt_number: str
    amount_paise: int
    mode: PaymentMode
    reference: Optional[str] = None
    mode_details: Optional[Dict[str, Any]] = None
    received_at: datetime
    received_by_name: str
    is_refund: bool
    refund_reason: Optional[str] = None
    # A struck receipt must be distinguishable from a live one, or a screen
    # listing payments will show money that no longer counts.
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    visit_id: Optional[uuid.UUID] = None
    patient_id: uuid.UUID
    status: InvoiceStatus
    payer_type: PayerType
    gross_paise: int
    discount_paise: int
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
    paid_paise: int
    payer_covered_paise: int
    discount_reason: Optional[str] = None
    issued_at: Optional[datetime] = None
    consultant_id: Optional[uuid.UUID] = None
    doctor_name: str = ""
    organisation_id: Optional[uuid.UUID] = None
    # Why anything on this bill was priced as it was: a free follow-up, an
    # agreed rate. A zero that cannot explain itself is indistinguishable
    # from a bug.
    pricing_notes: Optional[List[str]] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    # The correction trail. A bill amended before payment, or cancelled and
    # reinstated, is a fact somebody may have to explain later.
    amended_at: Optional[datetime] = None
    amendment_reason: Optional[str] = None
    amendment_count: int = 0
    # Set once a consultant payout has counted this invoice. After that
    # nothing about it may be corrected.
    payout_locked_at: Optional[datetime] = None
    created_by_name: str = ""
    created_at: datetime
    lines: List[InvoiceLineOut] = []
    payments: List[PaymentOut] = []


class PaymentRequest(BaseModel):
    amount_paise: int = Field(gt=0)
    mode: PaymentMode
    reference: Optional[str] = Field(default=None, max_length=120)
    # What the instrument itself needs: a cheque number and bank, a card's
    # last four, a UPI reference. Checked against the mode in
    # app/billing/payment_modes.py, which is also what the screen renders
    # its fields from, so the two cannot disagree.
    mode_details: Optional[Dict[str, Any]] = None
    cash_session_id: Optional[uuid.UUID] = None


class RefundRequest(BaseModel):
    amount_paise: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    mode: PaymentMode = PaymentMode.CASH
    # Credit the patient instead of opening the drawer. The commonest refund
    # at an OPD counter is a test billed and not done, for somebody who will
    # be back on Thursday.
    to_wallet: bool = False


class WalletDepositRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_paise: int = Field(gt=0)
    mode: PaymentMode = PaymentMode.CASH
    mode_details: Optional[Dict[str, Any]] = None
    reason: Optional[str] = Field(default=None, max_length=255)


class WalletWithdrawRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_paise: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class WalletPayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_paise: int = Field(gt=0)


class WalletEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: WalletEntryKind
    amount_paise: int
    balance_after_paise: int
    invoice_id: Optional[uuid.UUID] = None
    receipt_number: Optional[str] = None
    reason: Optional[str] = None
    created_by_name: str = ""
    created_at: datetime


class WalletOut(BaseModel):
    patient_id: uuid.UUID
    balance_paise: int
    entries: List[WalletEntryOut] = []


class CancelInvoiceRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class InvoiceSummaryOut(BaseModel):
    """One line in a bill list: enough to recognise it without opening it."""

    id: uuid.UUID
    invoice_number: str
    status: InvoiceStatus
    patient_id: uuid.UUID
    patient_name: str
    uhid: Optional[str] = None
    visit_number: Optional[str] = None
    visit_id: Optional[uuid.UUID] = None
    total_paise: int
    paid_paise: int
    balance_paise: int
    amendment_count: int = 0
    payout_locked: bool = False
    issued_at: Optional[datetime] = None
    created_at: datetime


class InvoiceListOut(BaseModel):
    total: int
    items: List[InvoiceSummaryOut] = []


class AmendInvoiceRequest(BaseModel):
    """Replace what a bill charges for, before anybody has paid it.

    The lines are sent whole rather than as a patch. A bill is a snapshot of
    what was charged, and applying a partial update risks leaving a line from
    the previous version that nobody meant to keep.
    """

    model_config = ConfigDict(extra="forbid")

    items: List[InvoiceItemRequest]
    invoice_discount_paise: int = Field(default=0, ge=0)
    discount_reason: Optional[str] = Field(default=None, max_length=255)
    reason: str = Field(min_length=3, max_length=500)


# ----------------------------------------------------- registration bundle
class RegisterAndBillRequest(BaseModel):
    """The whole counter workflow in one call.

    Reception does registration, visit and billing as a single action, and a
    partial result — a visit with no bill, or a patient with no visit — is
    exactly the mess that has to be untangled by hand later. One transaction.
    """

    # Either an existing patient, or the details to create one.
    patient_id: Optional[uuid.UUID] = None
    new_patient: Optional[PatientRegisterRequest] = None

    department: Department
    doctor_id: Optional[uuid.UUID] = None
    doctor_name: str = ""
    visit_type: VisitType = VisitType.NEW
    payer_type: PayerType = PayerType.SELF_PAY
    organisation_id: Optional[uuid.UUID] = None
    referred_by: Optional[str] = None

    items: List[InvoiceItemRequest] = Field(min_length=1)
    invoice_discount_paise: int = Field(default=0, ge=0)
    discount_reason: Optional[str] = None

    # Collect at the counter in the same step, when the patient pays now.
    payment: Optional[PaymentRequest] = None


class RegisterAndBillResponse(BaseModel):
    patient: PatientCardOut
    visit: VisitOut
    invoice: InvoiceOut
    payment: Optional[PaymentOut] = None


# ------------------------------------------------------------------ finance
class CashSessionOpenRequest(BaseModel):
    counter_name: str = Field(default="Reception", max_length=64)
    opening_float_paise: int = Field(default=0, ge=0)


class CashSessionCloseRequest(BaseModel):
    counted_cash_paise: int = Field(ge=0)
    variance_note: Optional[str] = Field(default=None, max_length=500)


class CashSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    counter_name: str
    cashier_name: str
    status: CashSessionStatus
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opening_float_paise: int
    counted_cash_paise: Optional[int] = None
    variance_paise: Optional[int] = None
    variance_note: Optional[str] = None


class CollectionSummaryOut(BaseModel):
    """The day's money, the way a hospital actually asks about it."""

    on: date
    invoice_count: int
    patient_count: int
    billed_paise: int
    discount_paise: int
    collected_paise: int
    refunded_paise: int
    outstanding_paise: int
    # Bills settled from credit the patient had already deposited. Reported
    # separately and deliberately kept out of `by_mode` and `collected_paise`:
    # that money was banked on the day it was deposited, and counting it
    # again here is how a day's takings stop matching the drawer.
    settled_from_wallet_paise: int = 0
    # Money that moved through the till today, by instrument. Sums to
    # collected_paise minus refunded_paise.
    by_mode: Dict[str, int]
    by_department: Dict[str, int]


# Insurance policies and claims: see app/api/v1/routes/insurance.py.
