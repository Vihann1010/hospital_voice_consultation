"""Request bodies for the operation theatre."""
import uuid
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Department

Milestone = Literal["wheel_in_at", "anaesthesia_start_at", "incision_at", "closure_at", "wheel_out_at"]


class TheatreRoomIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True
    notes: Optional[str] = Field(default=None, max_length=500)


class OperationIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    department: Optional[Department] = None
    grade: Optional[str] = None
    default_minutes: int = Field(default=60, ge=5, le=1440)
    service_code: Optional[str] = Field(default=None, max_length=32)
    is_active: bool = True
    notes: Optional[str] = Field(default=None, max_length=1000)


class SurgeryBookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: May be left out when booking for an admission: the admission names the patient.
    patient_id: Optional[uuid.UUID] = None
    admission_id: Optional[uuid.UUID] = None
    department: Optional[Department] = None
    operation_id: Optional[uuid.UUID] = None
    operation_name: Optional[str] = Field(default=None, max_length=255)
    laterality: str
    diagnosis: Optional[str] = Field(default=None, max_length=2000)
    surgeon_consultant_id: Optional[uuid.UUID] = None
    surgeon_name: Optional[str] = Field(default=None, max_length=255)
    assistants: List[str] = Field(default_factory=list, max_length=6)
    anaesthetist_name: Optional[str] = Field(default=None, max_length=255)
    anaesthesia_type: Optional[str] = None
    room_id: Optional[uuid.UUID] = None
    scheduled_at: datetime
    expected_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    priority: str = "elective"
    notes: Optional[str] = Field(default=None, max_length=2000)
    #: Book the room even though another case overlaps it.
    allow_overlap: bool = False


class SurgeryRescheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_at: Optional[datetime] = None
    room_id: Optional[uuid.UUID] = None
    expected_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    priority: Optional[str] = None
    allow_overlap: bool = False


class SurgeryCancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SurgeryTimeIn(BaseModel):
    milestone: Milestone
    #: When it happened. Omitted means now.
    at: Optional[datetime] = None
