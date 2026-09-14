"""API contracts for the Visit Pad (mirrors frontend/lib/padTypes.ts)."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Department, PadStatus


class PadDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: str
    title: str
    patient_id: uuid.UUID
    consultation_id: Optional[uuid.UUID] = None
    admission_id: Optional[uuid.UUID] = None
    surgery_id: Optional[uuid.UUID] = None
    department: Optional[Department] = None
    layout_revision: int
    sections: List[Dict[str, Any]]
    values: Dict[str, Any]
    provenance: Dict[str, Any]
    status: PadStatus
    author_name: str
    signed_by_name: Optional[str] = None
    signed_at: Optional[datetime] = None
    group_id: uuid.UUID
    version: int
    supersedes_id: Optional[uuid.UUID] = None
    amendment_reason: Optional[str] = None
    print_count: int
    serial_number: Optional[str] = None
    order_item_id: Optional[uuid.UUID] = None
    paper_signed_at: Optional[datetime] = None
    paper_signed_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PadDocumentSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: str
    title: str
    consultation_id: Optional[uuid.UUID] = None
    admission_id: Optional[uuid.UUID] = None
    surgery_id: Optional[uuid.UUID] = None
    order_item_id: Optional[uuid.UUID] = None
    serial_number: Optional[str] = None
    paper_signed_at: Optional[datetime] = None
    status: PadStatus
    version: int
    author_name: str
    signed_by_name: Optional[str] = None
    signed_at: Optional[datetime] = None
    created_at: datetime


class PadSaveIn(BaseModel):
    values: Dict[str, Any]
    #: The `updated_at` the browser last received. A save based on an older
    #: copy is refused so one doctor cannot overwrite another's changes.
    base_updated_at: Optional[datetime] = None


class PadArrangementItem(BaseModel):
    key: str
    visible_in_pad: bool = True
    visible_in_print: bool = True


class PadArrangeIn(BaseModel):
    sections: List[PadArrangementItem]


class PadAmendIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class PadTemplateIn(BaseModel):
    document_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=500)
    shared: bool = False


class PadTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: str
    name: str
    description: Optional[str] = None
    owner_name: str
    shared: bool
    use_count: int
    section_keys: List[str]


class PadApplyTemplateIn(BaseModel):
    template_id: uuid.UUID
    replace: bool = False


LayoutScope = Literal["personal", "department", "hospital"]


class PadLayoutOut(BaseModel):
    document_type: str
    document_label: str
    scope: Literal["personal", "department", "hospital", "default"]
    name: str
    sections: List[Dict[str, Any]]
    revision: int
    updated_by_name: Optional[str] = None
    variables: Dict[str, str]
    #: Section key -> field keys that must stay (see PROTECTED_SECTIONS).
    protected: Dict[str, List[str]] = {}
    #: Certificates, consents and radiology reports: the layout is fixed.
    locked: bool = False


class PadLayoutIn(BaseModel):
    scope: LayoutScope
    name: str = Field(default="", max_length=160)
    sections: List[Dict[str, Any]]
    department: Optional[Department] = None


class CatalogueSuggestionOut(BaseModel):
    text: str
    use_count: int
