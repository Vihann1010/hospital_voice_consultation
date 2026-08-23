"""API request/response contracts (Pydantic v2)."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import ConsultationStatus, Department, Gender, TurnRole, UserRole


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    department: Optional[Department] = None
    is_active: bool


# --------------------------------------------------------------------------
# Patients
# --------------------------------------------------------------------------
class PatientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    age: int = Field(ge=0, le=120)
    gender: Gender
    phone_number: str = Field(min_length=8, max_length=20)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.replace(" ", "").replace("-", "")
        digits = cleaned[1:] if cleaned.startswith("+") else cleaned
        if not digits.isdigit():
            raise ValueError("Phone number may contain digits, spaces, '-' and a leading '+'.")
        return cleaned


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    age: int
    gender: Gender
    phone_number: str
    created_at: datetime


# --------------------------------------------------------------------------
# Consultations
# --------------------------------------------------------------------------
class ConsultationStartRequest(BaseModel):
    patient: PatientCreate
    department: Department


class ConsultationStartFromVisitRequest(BaseModel):
    """Begin voice intake for someone reception already registered.

    Only the visit is needed: the patient, their department and their
    demographics are already on the record, and re-typing them at a second
    screen is how the same person ends up in the system twice.
    """

    visit_id: uuid.UUID


class ConsultationStartResponse(BaseModel):
    consultation_id: uuid.UUID
    patient_id: uuid.UUID
    department: Department
    session_token: str
    ws_path: str


class ConversationTurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: TurnRole
    content: str
    sequence: int
    interrupted: bool
    created_at: datetime


class ConsultationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    department: Department
    status: ConsultationStatus
    medical_json: Optional[Dict[str, Any]] = None
    transcript: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None


class ConsultationDetailOut(ConsultationOut):
    patient: PatientOut
    turns: List[ConversationTurnOut] = []


class ConsultationListItemOut(ConsultationOut):
    """List rows carry the patient inline so tables render in one request."""

    patient: Optional[PatientOut] = None
    reviewed_at: Optional[str] = None


class ConsultationListOut(BaseModel):
    items: List[ConsultationListItemOut]
    total: int


class ConsultationStatsOut(BaseModel):
    in_progress: int = 0
    completed: int = 0
    abandoned: int = 0
    last_24h: int = 0
    waiting: int = 0


# --------------------------------------------------------------------------
# Patient directory & history
# --------------------------------------------------------------------------
class PatientListItemOut(PatientOut):
    visit_count: int = 0
    visit_reason: Optional[str] = None
    payment_status: Optional[str] = None


class PatientListOut(BaseModel):
    items: List[PatientListItemOut]
    total: int


class PatientVisitOut(BaseModel):
    consultation_id: uuid.UUID
    department: Department
    status: ConsultationStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    chief_complaint: Optional[str] = None
    overall_risk: Optional[str] = None
    one_liner: Optional[str] = None


class PatientHistoryOut(BaseModel):
    patient: PatientOut
    summary: Dict[str, Any]
    visits: List[PatientVisitOut]


# --------------------------------------------------------------------------
# Copilot
# --------------------------------------------------------------------------
class CopilotDecisionRequest(BaseModel):
    item_key: str = Field(min_length=1, max_length=200)
    decision: str = Field(pattern="^(accepted|dismissed|pending)$")
    note: Optional[str] = Field(default=None, max_length=1000)


class CopilotDecisionOut(BaseModel):
    item_key: str
    decision: str
    note: Optional[str] = None
    doctor_name: Optional[str] = None
    at: Optional[str] = None


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------
class HealthOut(BaseModel):
    status: str
    app: str
    environment: str
    database: str
    version: str = "1.0.0"
