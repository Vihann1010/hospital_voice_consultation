"""Request and response shapes for booking and the queue board."""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AppointmentStatus, Gender, VisitType


class CallerDetails(BaseModel):
    """Somebody who rang and is not on the register yet.

    Age and gender are optional here on purpose. Over a telephone they are
    the two fields most often guessed, and they are asked properly at the
    desk during registration; requiring them would only encourage the clerk
    to invent them.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    phone_number: str = Field(min_length=10, max_length=20)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    gender: Optional[Gender] = None


class AppointmentBookRequest(BaseModel):
    # Unknown keys are refused rather than dropped: a screen sending a field
    # this endpoint has never heard of is a bug, and silently ignoring it
    # produces a booking that is missing something the clerk typed.
    model_config = ConfigDict(extra="forbid")

    # One or the other. A registered patient is linked by id; anyone else is
    # booked under the name and number they gave on the phone.
    patient_id: Optional[uuid.UUID] = None
    caller: Optional[CallerDetails] = None
    consultant_id: uuid.UUID
    scheduled_start: datetime
    visit_type: VisitType = VisitType.NEW
    reason: Optional[str] = Field(default=None, max_length=2000)
    referred_by: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _one_of(self) -> "AppointmentBookRequest":
        if (self.patient_id is None) == (self.caller is None):
            raise ValueError(
                "Book against an existing patient, or give the caller's name and "
                "number - not both, and not neither."
            )
        return self


class AppointmentRescheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_start: datetime


class AppointmentCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class AppointmentStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AppointmentStatus


class CheckInRegistration(BaseModel):
    """The minimum a patient record needs, asked at the desk."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    age: int = Field(ge=0, le=120)
    gender: Gender
    phone_number: str = Field(min_length=10, max_length=20)
    city: Optional[str] = Field(default=None, max_length=120)


class AppointmentCheckInRequest(BaseModel):
    """Turning a booking into an attendance.

    The consultant, department and visit type are not repeated here — they
    are already on the booking, and letting the check-in restate them is how
    a patient ends up registered against a doctor they did not book.

    For a phone booking this is also the moment of registration, which is
    why it can carry either the details to create a patient record or the id
    of the existing one the clerk recognised.
    """

    model_config = ConfigDict(extra="forbid")

    notes: Optional[str] = Field(default=None, max_length=2000)
    # The caller turned out to be someone already on the register.
    patient_id: Optional[uuid.UUID] = None
    # The caller is new. Age and gender become mandatory here, because now
    # there is a person at the desk to ask. Named to match the counter's own
    # register-and-bill payload rather than inventing a second vocabulary.
    new_patient: Optional[CheckInRegistration] = None

    @model_validator(mode="after")
    def _not_both(self) -> "AppointmentCheckInRequest":
        if self.patient_id is not None and self.new_patient is not None:
            raise ValueError(
                "Either link the patient you found, or register a new one - not both."
            )
        return self


class SlotOut(BaseModel):
    start: datetime
    end: datetime
    available: bool
    past: bool
    appointment_id: Optional[uuid.UUID] = None


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_age: Optional[int] = None
    caller_gender: Optional[Gender] = None
    consultant_id: uuid.UUID
    consultant_name: str
    department: str
    scheduled_start: datetime
    duration_minutes: int
    status: AppointmentStatus
    visit_type: VisitType
    visit_id: Optional[uuid.UUID] = None
    reason: Optional[str] = None
    referred_by: Optional[str] = None
    booked_by_name: str = ""
    cancellation_reason: Optional[str] = None


class BoardRowOut(BaseModel):
    """One line on the queue board — a booking or a walk-in."""

    id: Optional[uuid.UUID] = None
    kind: str
    visit_id: Optional[uuid.UUID] = None
    visit_number: Optional[str] = None
    token_number: Optional[int] = None
    patient_id: Optional[uuid.UUID] = None
    patient_name: str
    uhid: str
    # False for a phone booking nobody has registered yet. The board uses
    # this to offer "Register & check in" instead of "Check in".
    registered: bool = True
    phone_number: Optional[str] = None
    consultant_name: str
    department: str
    scheduled_start: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    visit_type: str
    reason: Optional[str] = None
    status: AppointmentStatus


class BoardOut(BaseModel):
    date: date
    counts: Dict[str, int]
    rows: List[BoardRowOut]


class NextSlotOut(BaseModel):
    consultant_id: uuid.UUID
    next_available: Optional[datetime] = None

