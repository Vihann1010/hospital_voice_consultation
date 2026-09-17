"""Running and configuring the front-office reports.

**Who may see whose money.** Two of these reports — the cash ledger and the
daily closing — are things a cashier needs at the end of their own shift, so
they are reachable with counter rights and forced to that person's own till.
Seeing anybody else's, or running the four hospital-wide reports at all,
needs finance rights and the finance PIN. That distinction is the point: a
receptionist counting their drawer is not the same act as reading the
hospital's takings.
"""
import uuid
from datetime import date, timedelta
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbSession, require_permission
from app.api.v1.routes.finance import finance_unlock
from app.core.clock import local_today
from app.core.permissions import Permission, has_permission
from app.models.reporting import ReportColumnSetting
from app.reports import catalogue, get as get_spec
from app.reports.runner import run as run_report, to_csv, visible_columns

router = APIRouter(prefix="/reports", tags=["reports"])

# The gate on the endpoints is only "may open patient records"; which report
# a person may actually run is decided per report by `_may_run`, because the
# surgical register is a clinical report and the cash ledger is not.
READ_REPORTS = require_permission(Permission.PATIENT_READ)


def _may_run(user, spec) -> bool:
    if spec.permission:
        return has_permission(user.role, Permission(spec.permission))
    if not has_permission(user.role, Permission.INVOICE_READ):
        return False
    return has_permission(user.role, Permission.FINANCE_READ) or spec.self_service
CONFIGURE = require_permission(Permission.SYSTEM_ADMIN)

# Nobody should be able to ask for five years of receipts in one request and
# take the database down with it.
MAX_RANGE_DAYS = 366


class ReportColumnOut(BaseModel):
    key: str
    label: str
    type: str
    total: bool
    visible: bool
    position: int


class ReportOut(BaseModel):
    key: str
    title: str
    description: str
    date_from: date
    date_to: date
    #: Set when the report was narrowed to one person's till.
    scoped_to: Optional[str] = None
    columns: List[ReportColumnOut]
    rows: List[Dict[str, Any]]
    totals: Dict[str, int]
    row_count: int


class ReportSummaryOut(BaseModel):
    key: str
    title: str
    description: str
    single_day: bool
    self_service: bool


class ColumnSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_key: str = Field(max_length=48)
    visible: bool = True
    position: int = Field(default=0, ge=0, le=99)


@router.get("", response_model=List[ReportSummaryOut],
            dependencies=[Depends(READ_REPORTS)])
async def list_reports(user: CurrentUser) -> List[ReportSummaryOut]:
    """The reports this person may run."""
    return [
        ReportSummaryOut(
            key=spec.key,
            title=spec.title,
            description=spec.description,
            single_day=spec.single_day,
            self_service=spec.self_service,
        )
        for spec in catalogue()
        if _may_run(user, spec)
    ]


async def _resolve(
    session: DbSession,
    user: CurrentUser,
    key: str,
    date_from: Optional[date],
    date_to: Optional[date],
    mine_only: bool,
) -> Dict[str, Any]:
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report")

    if not _may_run(user, spec):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You do not have access to this report." if spec.permission
            else "This report covers the whole hospital and needs finance rights.",
        )
    # A clinical report is never narrowed to someone's till.
    wide = has_permission(user.role, Permission.FINANCE_READ) or bool(spec.permission)

    today = local_today()
    to_day = date_to or today
    from_day = date_from or (to_day if spec.single_day else to_day - timedelta(days=6))
    if spec.single_day:
        from_day = to_day
    if from_day > to_day:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The start date is after the end date."
        )
    if (to_day - from_day).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Ask for at most {MAX_RANGE_DAYS} days at a time.",
        )

    # Without finance rights the report is forced to this person's own till,
    # whatever was asked for.
    scope = user.full_name if (mine_only or not wide) else None

    return await run_report(
        session, spec, date_from=from_day, date_to=to_day, user_name=scope
    )


@router.get("/{key}", response_model=ReportOut, dependencies=[Depends(READ_REPORTS)])
async def run(
    key: str,
    session: DbSession,
    user: CurrentUser,
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
    mine_only: bool = Query(default=False, alias="mine"),
) -> ReportOut:
    return ReportOut(**await _resolve(session, user, key, date_from, date_to, mine_only))


@router.get("/{key}/csv", dependencies=[Depends(READ_REPORTS)])
async def run_csv(
    key: str,
    session: DbSession,
    user: CurrentUser,
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
    mine_only: bool = Query(default=False, alias="mine"),
) -> Response:
    """The same report as a spreadsheet, with the same columns."""
    report = await _resolve(session, user, key, date_from, date_to, mine_only)
    filename = f"{key}-{report['date_from']}-to-{report['date_to']}.csv"
    return Response(
        content=to_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{key}/columns", response_model=List[ReportColumnOut],
            dependencies=[Depends(READ_REPORTS)])
async def report_columns(key: str, session: DbSession) -> List[ReportColumnOut]:
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report")
    return [ReportColumnOut(**column) for column in await visible_columns(session, spec)]


@router.put("/{key}/columns", response_model=List[ReportColumnOut],
            dependencies=[Depends(CONFIGURE)])
async def set_report_columns(
    key: str, payload: List[ColumnSettingIn], session: DbSession
) -> List[ReportColumnOut]:
    """Choose which columns this report shows, and in what order.

    Replaced wholesale, and unknown column keys are refused rather than
    stored — a typo would otherwise sit in the table forever, doing nothing
    and matching nothing.
    """
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report")

    known = {column.key for column in spec.columns}
    unknown = sorted({entry.column_key for entry in payload} - known)
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{spec.title} has no column called {', '.join(unknown)}.",
        )
    if not any(entry.visible for entry in payload):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A report needs at least one visible column.",
        )

    await session.execute(
        delete(ReportColumnSetting).where(ReportColumnSetting.report_key == key)
    )
    for entry in payload:
        session.add(ReportColumnSetting(report_key=key, **entry.model_dump()))
    await session.commit()

    return [ReportColumnOut(**column) for column in await visible_columns(session, spec)]
