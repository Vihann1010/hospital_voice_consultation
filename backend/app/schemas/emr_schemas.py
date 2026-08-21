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


class InvoiceCreateRequest(BaseModel):
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
    received_at: datetime
    received_by_name: str
    is_refund: bool
    refund_reason: Optional[str] = None


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
    cancelled_at: Optional[datetime] = None
    created_by_name: str = ""
    created_at: datetime
    lines: List[InvoiceLineOut] = []
    payments: List[PaymentOut] = []


class PaymentRequest(BaseModel):
    amount_paise: int = Field(gt=0)
    mode: PaymentMode
    reference: Optional[str] = Field(default=None, max_length=120)
    cash_session_id: Optional[uuid.UUID] = None


class RefundRequest(BaseModel):
    amount_paise: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    mode: PaymentMode = PaymentMode.CASH


class CancelInvoiceRequest(BaseModel):
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
    by_mode: Dict[str, int]
    by_department: Dict[str, int]


# ---------------------------------------------------------------- insurance
class PolicyUpsert(BaseModel):
    patient_id: uuid.UUID
    payer_type: PayerType = PayerType.INSURANCE
    insurer_name: str = Field(min_length=1, max_length=255)
    tpa_name: Optional[str] = Field(default=None, max_length=255)
    policy_number: str = Field(min_length=1, max_length=64)
    member_id: Optional[str] = Field(default=None, max_length=64)
    scheme_name: Optional[str] = Field(default=None, max_length=255)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    sum_insured_paise: Optional[int] = Field(default=None, ge=0)


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    payer_type: PayerType
    insurer_name: str
    tpa_name: Optional[str] = None
    policy_number: str
    member_id: Optional[str] = None
    scheme_name: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    sum_insured_paise: Optional[int] = None
    balance_paise: Optional[int] = None
    is_active: bool


class ClaimCreateRequest(BaseModel):
    policy_id: uuid.UUID
    visit_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None
    claimed_paise: int = Field(ge=0)
    diagnosis: Optional[str] = None
    treatment_summary: Optional[str] = None


class ClaimUpdateRequest(BaseModel):
    status: ClaimStatus
    external_reference: Optional[str] = Field(default=None, max_length=120)
    approved_paise: Optional[int] = Field(default=None, ge=0)
    settled_paise: Optional[int] = Field(default=None, ge=0)
    patient_liability_paise: Optional[int] = Field(default=None, ge=0)
    rejection_reason: Optional[str] = None
    query_detail: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_number: str
    policy_id: uuid.UUID
    patient_id: uuid.UUID
    visit_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None
    status: ClaimStatus
    external_reference: Optional[str] = None
    claimed_paise: int
    approved_paise: int
    settled_paise: int
    patient_liability_paise: int
    diagnosis: Optional[str] = None
    submitted_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    query_detail: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = []
    created_at: datetime
