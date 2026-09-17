"""Request bodies for the inpatient drug chart."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.ipd_schemas import MedicationOrderRequest


class DrugCheckIn(BaseModel):
    drug_name: str = Field(min_length=1, max_length=255)


class DrugOrderIn(MedicationOrderRequest):
    #: Serious alerts the doctor has read and accepted, as returned by the
    #: check endpoint. The order is refused while any remain unacknowledged.
    acknowledged_alerts: List[Dict[str, Any]] = Field(default_factory=list)


class GiveNowIn(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)
