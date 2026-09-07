"""IPD API contracts. Amounts are integer paise, matching storage."""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AdmissionStatus, AdmissionType, BedStatus, ChargeCategory, Department,
    DischargeType, MedicationRouteIPD, MedicationStatus, NoteType, WardType,
)


class WardUpsert(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=120)
    ward_type: WardType
    department: Optional[Department] = None
    floor: Optional[str] = Field(default=None, max_length=32)
    daily_rate_paise: int = Field(ge=0)
    nursing_rate_paise: int = Field(default=0, ge=0)
    is_active: bool = True


class BedUpsert(BaseModel):
    ward_id: uuid.UUID
    label: str = Field(min_length=1, max_length=32)
    rate_override_paise: Optional[int] = Field(default=None, ge=0)
    is_oxygen_supported: bool = False
    notes: Optional[str] = Field(default=None, max_length=255)


class BedStatusUpdate(BaseModel):
    status: BedStatus
    notes: Optional[str] = Field(default=None, max_length=255)


class AdmitRequest(BaseModel):
    patient_id: uuid.UUID
    bed_id: uuid.UUID
    department: Department
    admitting_doctor_id: Optional[uuid.UUID] = None
    admitting_doctor_name: str = ""
    admission_type: AdmissionType = AdmissionType.PLANNED
    provisional_diagnosis: Optional[str] = None
    reason_for_admission: Optional[str] = None
    expected_stay_days: Optional[int] = Field(default=None, ge=0, le=365)
    attendant_name: Optional[str] = Field(default=None, max_length=255)
    attendant_phone: Optional[str] = Field(default=None, max_length=20)
    attendant_relation: Optional[str] = Field(default=None, max_length=64)
    advance_paid_paise: int = Field(default=0, ge=0)
    visit_id: Optional[uuid.UUID] = None
    allergies: List[str] = Field(default_factory=list)


class TransferRequest(BaseModel):
    to_bed_id: uuid.UUID
    reason: Optional[str] = Field(default=None, max_length=255)


class AdmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ip_number: str
    patient_id: uuid.UUID
    department: Department
    admitting_doctor_name: str
    admission_type: AdmissionType
    status: AdmissionStatus
    admitted_at: datetime
    discharged_at: Optional[datetime] = None
    provisional_diagnosis: Optional[str] = None
    final_diagnosis: Optional[str] = None
    reason_for_admission: Optional[str] = None
    allergies: Optional[List[str]] = []
    attendant_name: Optional[str] = None
    attendant_phone: Optional[str] = None
    advance_paid_paise: int = 0
    discharge_type: Optional[DischargeType] = None
    created_at: datetime


class VitalsRequest(BaseModel):
    respiratory_rate: Optional[int] = Field(default=None, ge=1, le=99)
    spo2_percent: Optional[int] = Field(default=None, ge=50, le=100)
    on_oxygen: bool = False
    oxygen_litres: Optional[float] = Field(default=None, ge=0, le=60)
    systolic_bp: Optional[int] = Field(default=None, ge=40, le=300)
    diastolic_bp: Optional[int] = Field(default=None, ge=20, le=200)
    pulse: Optional[int] = Field(default=None, ge=20, le=250)
    temperature_c: Optional[float] = Field(default=None, ge=25.0, le=45.0)
    consciousness: Optional[str] = Field(default=None, max_length=1)
    spo2_scale_2: bool = False
    pain_score: Optional[int] = Field(default=None, ge=0, le=10)
    blood_sugar_mgdl: Optional[int] = Field(default=None, ge=10, le=900)
    urine_output_ml: Optional[int] = Field(default=None, ge=0, le=10000)


class VitalsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recorded_at: datetime
    recorded_by_name: str
    respiratory_rate: Optional[int] = None
    spo2_percent: Optional[int] = None
    on_oxygen: bool = False
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    pulse: Optional[int] = None
    temperature_c: Optional[float] = None
    consciousness: Optional[str] = None
    pain_score: Optional[int] = None
    news2_score: Optional[int] = None
    news2_risk: Optional[str] = None
    news2_detail: Optional[Dict[str, Any]] = None
    escalated: bool = False


class MedicationOrderRequest(BaseModel):
    drug_name: str = Field(min_length=1, max_length=255)
    generic_name: Optional[str] = Field(default=None, max_length=255)
    strength: Optional[str] = Field(default=None, max_length=64)
    dose: str = Field(min_length=1, max_length=64)
    route: MedicationRouteIPD = MedicationRouteIPD.ORAL
    frequency_code: str = Field(default="OD", max_length=16)
    schedule_times: List[str] = Field(default_factory=list)
    is_stat: bool = False
    is_sos: bool = False
    instructions: Optional[str] = None


class MedicationAdministrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    due_at: datetime
    given_at: Optional[datetime] = None
    given_by_name: str = ""
    was_given: Optional[bool] = None
    omission_reason: Optional[str] = None


class MedicationOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    drug_name: str
    generic_name: Optional[str] = None
    strength: Optional[str] = None
    dose: str
    route: MedicationRouteIPD
    frequency_code: str
    schedule_times: Optional[List[str]] = []
    status: MedicationStatus
    started_at: datetime
    stopped_at: Optional[datetime] = None
    is_stat: bool = False
    is_sos: bool = False
    instructions: Optional[str] = None
    ordered_by_name: str = ""
    administrations: List[MedicationAdministrationOut] = []


class AdministerRequest(BaseModel):
    was_given: bool
    omission_reason: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None


class NoteRequest(BaseModel):
    note_type: NoteType
    content: str = Field(min_length=1)
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note_type: NoteType
    author_name: str
    author_role: str
    content: str
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    ai_generated: bool = False
    ai_reviewed_by_name: Optional[str] = None
    created_at: datetime


class ChargeRequest(BaseModel):
    category: ChargeCategory
    description: str = Field(min_length=1, max_length=255)
    unit_rate_paise: Optional[int] = Field(default=None, ge=0)
    quantity: int = Field(default=1, ge=1, le=999)
    service_item_id: Optional[uuid.UUID] = None
    service_code: Optional[str] = Field(default=None, max_length=32)
    notes: Optional[str] = None


class ChargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: ChargeCategory
    charged_on: date
    description: str
    quantity: int
    unit_rate_paise: int
    total_paise: int
    is_billed: bool
    posted_by_name: str
    created_at: datetime


class DischargeRequest(BaseModel):
    discharge_type: DischargeType = DischargeType.ROUTINE
    final_diagnosis: Optional[str] = None


class ReviewSummaryRequest(BaseModel):
    """A clinician accepting an AI draft, with any edits they made."""

    content: str = Field(min_length=1)
