"""API contracts for the investigation module."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AbnormalFlag,
    Department,
    InvestigationCategory,
    InvestigationPriority,
    OrderStatus,
    DocumentKind,
    ReportStatus,
)


# ------------------------------------------------------------------ catalog
class InvestigationOut(BaseModel):
    code: str
    name: str
    category: InvestigationCategory
    category_label: str
    aliases: List[str] = []
    specimen_or_site: Optional[str] = None
    preparation: Optional[str] = None
    turnaround: Optional[str] = None
    departments: List[Department] = []
    note: Optional[str] = None


class PanelOut(BaseModel):
    code: str
    name: str
    description: str
    members: List[InvestigationOut] = []


class CategoryOut(BaseModel):
    value: str
    label: str
    count: int


class CatalogOut(BaseModel):
    categories: List[CategoryOut]
    investigations: List[InvestigationOut]
    panels: List[PanelOut]
    total: int


class RecentInvestigationOut(BaseModel):
    code: str
    name: str
    uses: int


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    department: Optional[Department] = None
    codes: List[str] = []
    shared: bool = False


class WorkspaceOut(BaseModel):
    favorites: List[str] = []
    recent: List[RecentInvestigationOut] = []
    templates: List[TemplateOut] = []
    capabilities: Dict[str, Any] = {}


class FavoriteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    favorite: bool = True


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    codes: List[str] = Field(min_length=1)
    description: Optional[str] = Field(default=None, max_length=500)
    shared: bool = False


# ------------------------------------------------------------------- orders
class OrderCreateRequest(BaseModel):
    patient_id: uuid.UUID
    consultation_id: Optional[uuid.UUID] = None
    codes: List[str] = Field(min_length=1, description="Investigation and/or panel codes")
    priority: InvestigationPriority = InvestigationPriority.ROUTINE
    clinical_notes: Optional[str] = Field(default=None, max_length=2000)
    provisional_diagnosis: Optional[str] = Field(default=None, max_length=500)
    item_instructions: Dict[str, str] = {}


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    category: InvestigationCategory
    specimen_or_site: Optional[str] = None
    preparation: Optional[str] = None
    instructions: Optional[str] = None
    position: int
    reported: bool


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    consultation_id: Optional[uuid.UUID] = None
    department: Department
    status: OrderStatus
    priority: InvestigationPriority
    clinical_notes: Optional[str] = None
    provisional_diagnosis: Optional[str] = None
    ordered_by_name: str
    issued_at: Optional[datetime] = None
    created_at: datetime
    items: List[OrderItemOut] = []


class OrderListOut(BaseModel):
    items: List[OrderOut]
    total: int


# ------------------------------------------------------------------ reports
class ReportResultOut(BaseModel):
    printed_name: str
    display_name: str
    analyte_key: Optional[str] = None
    value: Optional[float] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    reference_text: Optional[str] = None
    reference_source: str = "none"
    flag: AbnormalFlag = AbnormalFlag.UNKNOWN
    deviation_note: Optional[str] = None
    note: Optional[str] = None
    section: Optional[str] = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    consultation_id: Optional[uuid.UUID] = None
    order_id: Optional[uuid.UUID] = None
    group_id: uuid.UUID
    version: int
    replaces_id: Optional[uuid.UUID] = None
    revision_note: Optional[str] = None
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    document_kind: Optional[DocumentKind] = None
    status: ReportStatus
    extraction_method: Optional[str] = None
    page_count: Optional[int] = None
    analysis: Optional[Dict[str, Any]] = None
    error_detail: Optional[str] = None
    uploaded_by_name: str
    created_at: datetime


class ReportListItemOut(BaseModel):
    """Lighter row for lists: analysis headline without the full result table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    version: int
    title: str
    original_filename: str
    content_type: str
    document_kind: Optional[DocumentKind] = None
    status: ReportStatus
    abnormal_count: int = 0
    critical_count: int = 0
    #: "clear", "unclear" or "not_analysed". The list needs this because a
    #: report nobody could read has no counts to show and must still be
    #: distinguishable from one that was read and found normal.
    clarity: Optional[str] = None
    headline: Optional[str] = None
    #: Set when part of the document was read and part was not.
    needs_manual_check: bool = False
    uploaded_by_name: str
    created_at: datetime


class ReportListOut(BaseModel):
    items: List[ReportListItemOut]
    total: int


class ReportVersionHistoryOut(BaseModel):
    group_id: uuid.UUID
    current: ReportOut
    versions: List[ReportListItemOut]
