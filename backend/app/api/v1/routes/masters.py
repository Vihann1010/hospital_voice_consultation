"""The registers: consultants and referral providers.

Reading is everyday work — reception picks a consultant on every registration.
Editing is a pricing control, because a consultant's free-follow-up window and
consultation fee decide what a returning patient is charged, so it sits with
the same role that owns the tariff.

Nothing here is ever deleted. A consultant who has left still signed the
prescriptions in the record and still appears in last year's payout, so they
are deactivated and drop out of the pickers instead.
"""
import uuid
from datetime import date, time
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

from app.api.deps import DbSession, require_permission
from app.core import financial_year
from app.core.permissions import Permission
from app.models.consultant import Consultant, ReferralProvider
from app.models.emr import ServiceItem
from app.models.organisation import NegotiatedRate, Organisation
from app.models.patient import PatientFieldSetting
from app.models.printing import PrintSetting
from app.printing.layout import PAGE_HEIGHT
from app.models.enums import Department, PayerType

router = APIRouter(prefix="/masters", tags=["masters"])

READ_MASTERS = require_permission(Permission.MASTER_READ)
MANAGE_MASTERS = require_permission(Permission.MASTER_MANAGE)


class ConsultantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    department: Department
    qualification: Optional[str] = None
    registration_number: Optional[str] = None
    phone_number: Optional[str] = None
    user_id: Optional[uuid.UUID] = None
    appointment_minutes: int
    first_consultation_free: bool
    opd_start_time: time
    opd_end_time: time
    opd_days: str
    free_follow_up_days: int
    consultation_service_code: Optional[str] = None
    payout_share_percent: int
    is_active: bool


class ConsultantUpsert(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    department: Department
    qualification: Optional[str] = Field(default=None, max_length=255)
    registration_number: Optional[str] = Field(default=None, max_length=120)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    user_id: Optional[uuid.UUID] = None
    # A slot has to be long enough to be a consultation and short enough to be
    # a working day; outside this range it is a typo, not a decision.
    appointment_minutes: int = Field(default=15, ge=5, le=120)
    # Waives this consultant's own fee the first time they see a patient.
    first_consultation_free: bool = False
    # When they sit. The scheduler offers slots inside this window only, so
    # getting it wrong shows up immediately as an empty or impossible day.
    opd_start_time: time = time(9, 0)
    opd_end_time: time = time(17, 0)
    # ISO weekday numbers, Monday 1 to Sunday 7. Six days by default, which is
    # how this OPD runs.
    opd_days: str = Field(default="1,2,3,4,5,6", pattern=r"^[1-7](,[1-7])*$")
    free_follow_up_days: int = Field(default=0, ge=0, le=365)
    consultation_service_code: Optional[str] = Field(default=None, max_length=32)
    payout_share_percent: int = Field(default=0, ge=0, le=100)
    is_active: bool = True


    @model_validator(mode="after")
    def _hours_run_forwards(self) -> "ConsultantUpsert":
        # Left unchecked this is silent: the slot loop simply produces nothing
        # and the booking screen shows an empty day with no explanation.
        if self.opd_end_time <= self.opd_start_time:
            raise ValueError("OPD hours must end after they start.")
        return self


class ReferralProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    clinic_name: Optional[str] = None
    phone_number: Optional[str] = None
    city: Optional[str] = None
    is_active: bool


class ReferralProviderUpsert(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    clinic_name: Optional[str] = Field(default=None, max_length=255)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    city: Optional[str] = Field(default=None, max_length=120)
    is_active: bool = True


# ------------------------------------------------------------ print setup
class PrintSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_type: str
    margin_top: int
    margin_bottom: int
    margin_left: int
    margin_right: int
    font_family: str
    font_size: int
    header_image: Optional[str] = None
    header_height: int
    footer_image: Optional[str] = None
    footer_height: int
    footer_remark: Optional[str] = None
    watermark_duplicates: bool


class PrintSettingUpdate(BaseModel):
    # Bounded so a mistyped margin cannot push the content off the page or
    # collapse it to nothing — either produces a document nobody notices is
    # wrong until a patient is holding it.
    margin_top: int = Field(default=42, ge=0, le=200)
    margin_bottom: int = Field(default=42, ge=0, le=200)
    margin_left: int = Field(default=42, ge=0, le=200)
    margin_right: int = Field(default=42, ge=0, le=200)
    font_family: str = Field(default="Helvetica", max_length=64)
    font_size: int = Field(default=9, ge=6, le=18)
    header_image: Optional[str] = Field(default=None, max_length=255)
    header_height: int = Field(default=0, ge=0, le=300)
    footer_image: Optional[str] = Field(default=None, max_length=255)
    footer_height: int = Field(default=0, ge=0, le=300)
    footer_remark: Optional[str] = Field(default=None, max_length=300)
    watermark_duplicates: bool = True


@router.get("/print-settings", response_model=List[PrintSettingOut],
            dependencies=[Depends(READ_MASTERS)])
async def list_print_settings(session: DbSession) -> List[PrintSettingOut]:
    result = await session.execute(
        select(PrintSetting).order_by(PrintSetting.document_type)
    )
    return [PrintSettingOut.model_validate(s) for s in result.scalars().all()]


@router.put("/print-settings/{document_type}", response_model=PrintSettingOut,
            dependencies=[Depends(MANAGE_MASTERS)])
async def update_print_setting(
    document_type: str, payload: PrintSettingUpdate, session: DbSession
) -> PrintSettingOut:
    """Change how one kind of document prints.

    Created on demand, so a document type that has never been configured can
    be set up without a migration.
    """
    setting = (
        await session.execute(
            select(PrintSetting).where(PrintSetting.document_type == document_type)
        )
    ).scalar_one_or_none()
    if setting is None:
        setting = PrintSetting(document_type=document_type)
        session.add(setting)

    # Side margins cannot squeeze the page out on their own — each is capped
    # at 200pt and A4 is 595 wide, so the pair always leaves room. The
    # vertical case is different: margins plus letterhead heights can add up
    # to more than the page, and then the document has nowhere to print.
    if (
        payload.margin_top + payload.header_height
        + payload.margin_bottom + payload.footer_height
        >= PAGE_HEIGHT - 150
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The header and footer together leave no room for the content.",
        )

    for field, value in payload.model_dump().items():
        setattr(setting, field, value)
    await session.commit()
    await session.refresh(setting)
    return PrintSettingOut.model_validate(setting)


# ----------------------------------------------------- patient field setup
class PatientFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_key: str
    visibility: str
    label: Optional[str] = None
    display_order: int


class PatientFieldUpdate(BaseModel):
    field_key: str = Field(min_length=1, max_length=64)
    visibility: Literal["required", "optional", "hidden"]
    label: Optional[str] = Field(default=None, max_length=120)
    display_order: int = Field(default=100, ge=0, le=1000)


@router.get("/patient-fields", response_model=List[PatientFieldOut],
            dependencies=[Depends(READ_MASTERS)])
async def list_patient_fields(session: DbSession) -> List[PatientFieldOut]:
    """What the registration form asks for, in the order it asks.

    Read by the form itself, so it is available to everyone who registers a
    patient rather than only to whoever configured it.
    """
    result = await session.execute(
        select(PatientFieldSetting).order_by(PatientFieldSetting.display_order)
    )
    return [PatientFieldOut.model_validate(f) for f in result.scalars().all()]


@router.put("/patient-fields", response_model=List[PatientFieldOut],
            dependencies=[Depends(MANAGE_MASTERS)])
async def update_patient_fields(
    payload: List[PatientFieldUpdate], session: DbSession
) -> List[PatientFieldOut]:
    """Replace the form's configuration in one go.

    Sent whole rather than field by field: the display order is a property of
    the list, and saving one row at a time would leave the form in a
    half-reordered state if the second save failed.
    """
    # Checked before anything is written: a patient record with no name is not
    # a record, and there is no screen that could recover from it afterwards.
    if not any(i.field_key == "name" and i.visibility == "required" for i in payload):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The patient's name must stay required.",
        )

    known = {
        setting.field_key: setting
        for setting in (
            await session.execute(select(PatientFieldSetting))
        ).scalars().all()
    }
    for item in payload:
        setting = known.get(item.field_key)
        if setting is None:
            setting = PatientFieldSetting(field_key=item.field_key)
            session.add(setting)
        setting.visibility = item.visibility
        setting.label = item.label
        setting.display_order = item.display_order

    await session.commit()
    result = await session.execute(
        select(PatientFieldSetting).order_by(PatientFieldSetting.display_order)
    )
    return [PatientFieldOut.model_validate(f) for f in result.scalars().all()]


# --------------------------------------------------------- financial years
class FinancialYearOut(BaseModel):
    label: str
    start: date
    end: date
    is_current: bool


@router.get("/financial-years", response_model=List[FinancialYearOut],
            dependencies=[Depends(READ_MASTERS)])
async def list_financial_years() -> List[FinancialYearOut]:
    """The years staff may work in, newest first.

    Selected once at sign-in and carried for the session, because it scopes
    every report and every document number — a filter that has to be set again
    on each screen is a filter someone will forget.
    """
    return [
        FinancialYearOut(
            label=year.label, start=year.start, end=year.end, is_current=year.is_current
        )
        for year in financial_year.selectable()
    ]


# ------------------------------------------------------------- consultants
@router.get("/consultants", response_model=List[ConsultantOut],
            dependencies=[Depends(READ_MASTERS)])
async def list_consultants(
    session: DbSession,
    department: Optional[Department] = Query(default=None),
    active_only: bool = Query(default=True),
) -> List[ConsultantOut]:
    statement = select(Consultant).order_by(Consultant.department, Consultant.full_name)
    if department is not None:
        statement = statement.where(Consultant.department == department)
    if active_only:
        statement = statement.where(Consultant.is_active.is_(True))
    result = await session.execute(statement)
    return [ConsultantOut.model_validate(c) for c in result.scalars().all()]


@router.post("/consultants", response_model=ConsultantOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(MANAGE_MASTERS)])
async def create_consultant(payload: ConsultantUpsert, session: DbSession) -> ConsultantOut:
    consultant = Consultant(**payload.model_dump())
    session.add(consultant)
    await session.commit()
    await session.refresh(consultant)
    return ConsultantOut.model_validate(consultant)


@router.put("/consultants/{consultant_id}", response_model=ConsultantOut,
            dependencies=[Depends(MANAGE_MASTERS)])
async def update_consultant(
    consultant_id: uuid.UUID, payload: ConsultantUpsert, session: DbSession
) -> ConsultantOut:
    consultant = await session.get(Consultant, consultant_id)
    if consultant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such consultant.")
    for field, value in payload.model_dump().items():
        setattr(consultant, field, value)
    await session.commit()
    await session.refresh(consultant)
    return ConsultantOut.model_validate(consultant)


# ------------------------------------------------------- referral providers
@router.get("/referrers", response_model=List[ReferralProviderOut],
            dependencies=[Depends(READ_MASTERS)])
async def list_referrers(
    session: DbSession, active_only: bool = Query(default=True)
) -> List[ReferralProviderOut]:
    statement = select(ReferralProvider).order_by(ReferralProvider.full_name)
    if active_only:
        statement = statement.where(ReferralProvider.is_active.is_(True))
    result = await session.execute(statement)
    return [ReferralProviderOut.model_validate(r) for r in result.scalars().all()]


@router.post("/referrers", response_model=ReferralProviderOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(MANAGE_MASTERS)])
async def create_referrer(
    payload: ReferralProviderUpsert, session: DbSession
) -> ReferralProviderOut:
    provider = ReferralProvider(**payload.model_dump())
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return ReferralProviderOut.model_validate(provider)


@router.put("/referrers/{provider_id}", response_model=ReferralProviderOut,
            dependencies=[Depends(MANAGE_MASTERS)])
async def update_referrer(
    provider_id: uuid.UUID, payload: ReferralProviderUpsert, session: DbSession
) -> ReferralProviderOut:
    provider = await session.get(ReferralProvider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such referral provider.")
    for field, value in payload.model_dump().items():
        setattr(provider, field, value)
    await session.commit()
    await session.refresh(provider)
    return ReferralProviderOut.model_validate(provider)


# --------------------------------------------------------- organisations
class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    payer_type: PayerType
    contact_person: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    default_discount_percent: int
    credit_days: int
    is_active: bool


class OrganisationUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=255)
    payer_type: PayerType = PayerType.CORPORATE
    contact_person: Optional[str] = Field(default=None, max_length=255)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    address: Optional[str] = None
    # A hundred percent discount is a free scheme, which is legitimate; more
    # than that is a typo that would pay the patient to attend.
    default_discount_percent: int = Field(default=0, ge=0, le=100)
    credit_days: int = Field(default=0, ge=0, le=365)
    is_active: bool = True


class NegotiatedRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_item_id: uuid.UUID
    rate_paise: int
    notes: Optional[str] = None


class NegotiatedRateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_item_id: uuid.UUID
    rate_paise: int = Field(ge=0)
    notes: Optional[str] = Field(default=None, max_length=255)


@router.get("/organisations", response_model=List[OrganisationOut],
            dependencies=[Depends(READ_MASTERS)])
async def list_organisations(
    session: DbSession, active_only: bool = Query(default=False)
) -> List[OrganisationOut]:
    """Employers, TPAs and schemes the hospital has agreed rates with."""
    stmt = select(Organisation).order_by(Organisation.name)
    if active_only:
        stmt = stmt.where(Organisation.is_active.is_(True))
    result = await session.execute(stmt)
    return [OrganisationOut.model_validate(row) for row in result.scalars()]


@router.post("/organisations", response_model=OrganisationOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(MANAGE_MASTERS)])
async def create_organisation(
    payload: OrganisationUpsert, session: DbSession
) -> OrganisationOut:
    existing = await session.scalar(
        select(Organisation).where(Organisation.code == payload.code)
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{payload.code} is already used by {existing.name}.",
        )
    organisation = Organisation(**payload.model_dump())
    session.add(organisation)
    await session.commit()
    await session.refresh(organisation)
    return OrganisationOut.model_validate(organisation)


@router.put("/organisations/{organisation_id}", response_model=OrganisationOut,
            dependencies=[Depends(MANAGE_MASTERS)])
async def update_organisation(
    organisation_id: uuid.UUID, payload: OrganisationUpsert, session: DbSession
) -> OrganisationOut:
    organisation = await session.get(Organisation, organisation_id)
    if organisation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    clash = await session.scalar(
        select(Organisation).where(
            Organisation.code == payload.code, Organisation.id != organisation_id
        )
    )
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{payload.code} is already used by {clash.name}."
        )
    for field, value in payload.model_dump().items():
        setattr(organisation, field, value)
    await session.commit()
    await session.refresh(organisation)
    return OrganisationOut.model_validate(organisation)


@router.get("/organisations/{organisation_id}/rates",
            response_model=List[NegotiatedRateOut],
            dependencies=[Depends(READ_MASTERS)])
async def list_rates(
    organisation_id: uuid.UUID, session: DbSession
) -> List[NegotiatedRateOut]:
    result = await session.execute(
        select(NegotiatedRate).where(NegotiatedRate.organisation_id == organisation_id)
    )
    return [NegotiatedRateOut.model_validate(row) for row in result.scalars()]


@router.put("/organisations/{organisation_id}/rates",
            response_model=List[NegotiatedRateOut],
            dependencies=[Depends(MANAGE_MASTERS)])
async def replace_rates(
    organisation_id: uuid.UUID, payload: List[NegotiatedRateIn], session: DbSession
) -> List[NegotiatedRateOut]:
    """Replace an organisation's whole rate card.

    Sent whole rather than patched, because that is how a rate card arrives —
    as a renegotiated sheet, not as three amendments. Replacing wholesale
    also removes rates that have been dropped from the agreement, which a
    per-row update would silently leave in force.
    """
    organisation = await session.get(Organisation, organisation_id)
    if organisation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")

    seen: set = set()
    for entry in payload:
        if entry.service_item_id in seen:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "The same service appears twice in this rate card.",
            )
        seen.add(entry.service_item_id)
        if await session.get(ServiceItem, entry.service_item_id) is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "That service is not on the price list.",
            )

    await session.execute(
        delete(NegotiatedRate).where(NegotiatedRate.organisation_id == organisation_id)
    )
    for entry in payload:
        session.add(
            NegotiatedRate(organisation_id=organisation_id, **entry.model_dump())
        )
    await session.commit()

    result = await session.execute(
        select(NegotiatedRate).where(NegotiatedRate.organisation_id == organisation_id)
    )
    return [NegotiatedRateOut.model_validate(row) for row in result.scalars()]
