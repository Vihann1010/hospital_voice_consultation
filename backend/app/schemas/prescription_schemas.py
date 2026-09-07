"""API contracts for the prescription module."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    DeliveryChannel,
    DeliveryStatus,
    Department,
    PrescriptionStatus,
)


# ------------------------------------------------------------------ formulary
class MedicineOut(BaseModel):
    code: str
    name: str
    ingredients: List[str] = []
    form: str
    strengths: List[str] = []
    default_frequency: Optional[str] = None
    default_duration: Optional[str] = None
    default_timing: Optional[str] = None
    category: str
    note: Optional[str] = None


class FormularyOut(BaseModel):
    items: List[MedicineOut]
    total: int


# ------------------------------------------------------------------ dictation
class DictationRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=8000)
    patient_id: Optional[uuid.UUID] = None


class DictatedMedicineOut(BaseModel):
    raw_text: str
    name: str = ""
    formulary_code: Optional[str] = None
    generic: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    dosage: Optional[str] = None
    frequency_code: Optional[str] = None
    frequency_text: Optional[str] = None
    duration: Optional[str] = None
    timing: Optional[str] = None
    route: Optional[str] = None
    instructions: Optional[str] = None
    confidence: float = 0.0
    unmatched: bool = False
    substituted: bool = False
    warnings: List[str] = []


class DictationResponse(BaseModel):
    medicines: List[DictatedMedicineOut]
    alerts: List[Dict[str, Any]] = []
    transcript: str


# --------------------------------------------------------------------- safety
class SafetyCheckRequest(BaseModel):
    patient_id: uuid.UUID
    medicines: List[Dict[str, Any]] = []


class SafetyAlertOut(BaseModel):
    kind: str
    severity: str
    medicines: List[str] = []
    description: str
    suggested_action: Optional[str] = None
    detected_by: str = "rule"


class SafetyCheckResponse(BaseModel):
    alerts: List[SafetyAlertOut] = []
    blocking: int = 0
    known_allergies: List[str] = []


# --------------------------------------------------------------- prescription
class MedicineInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    formulary_code: Optional[str] = None
    generic: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    dosage: Optional[str] = None
    frequency_code: Optional[str] = None
    frequency_text: Optional[str] = None
    duration: Optional[str] = None
    timing: Optional[str] = None
    route: Optional[str] = None
    instructions: Optional[str] = None
    source: str = "manual"


class PrescriptionCreateRequest(BaseModel):
    patient_id: uuid.UUID
    consultation_id: Optional[uuid.UUID] = None
    medicines: List[MedicineInput] = []
    diagnosis: Optional[str] = Field(default=None, max_length=2000)
    cause: Optional[str] = Field(default=None, max_length=2000)
    chief_complaint: Optional[str] = Field(default=None, max_length=2000)
    clinical_findings: Optional[str] = Field(default=None, max_length=4000)
    investigations: List[str] = []
    general_instructions: Optional[str] = Field(default=None, max_length=4000)
    follow_up_notes: Optional[str] = Field(default=None, max_length=500)
    follow_up_date: Optional[datetime] = None
    dictation_transcript: Optional[str] = None
    acknowledged_alerts: List[Dict[str, Any]] = []
    issue: bool = True


class PrescriptionMedicineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    formulary_code: Optional[str] = None
    name: str
    generic: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    dosage: Optional[str] = None
    frequency_code: Optional[str] = None
    frequency_text: Optional[str] = None
    duration: Optional[str] = None
    timing: Optional[str] = None
    route: Optional[str] = None
    instructions: Optional[str] = None
    source: str


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: DeliveryChannel
    provider: str
    recipient: str
    status: DeliveryStatus
    attempts: int
    provider_message_id: Optional[str] = None
    error_detail: Optional[str] = None
    last_attempt_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    is_final: bool = False
    requested_by_name: str = ""
    created_at: datetime


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prescription_number: str
    patient_id: uuid.UUID
    consultation_id: Optional[uuid.UUID] = None
    department: Department
    status: PrescriptionStatus
    doctor_name: str
    doctor_qualification: Optional[str] = None
    doctor_registration: Optional[str] = None
    diagnosis: Optional[str] = None
    cause: Optional[str] = None
    chief_complaint: Optional[str] = None
    clinical_findings: Optional[str] = None
    investigations_advised: Optional[List[str]] = []
    general_instructions: Optional[str] = None
    follow_up_notes: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    dictation_transcript: Optional[str] = None
    pdf_filename: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    issued_at: Optional[datetime] = None
    created_at: datetime
    medicines: List[PrescriptionMedicineOut] = []
    deliveries: List[DeliveryOut] = []


class PrescriptionListOut(BaseModel):
    items: List[PrescriptionOut]
    total: int


class SendWhatsAppRequest(BaseModel):
    phone_number: Optional[str] = Field(default=None, max_length=24)
