"""One shape for every report.

The old system had dozens of reports, each with its own screen, its own
column set, and its own idea of what a total was. Rebuilding that shape by
shape would mean writing the same date filter, the same CSV writer and the
same "which columns are visible" logic six times, and then again for the lab
and accounts reports in Parts 4 and 5.

So a report here is data: a list of columns and a function that returns rows.
Everything around it — filtering, totalling, hiding columns, exporting — is
written once and applies to all of them.

**Money is formatted at the edge, never in the query.** Rows carry integer
paise, exactly as the database holds them, and the column's declared type
decides how it is rendered. A report that returned "₹1,234.00" as a string
could not be summed, sorted or exported to a spreadsheet.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ColumnType(str, Enum):
    TEXT = "text"
    MONEY = "money"          # integer paise
    NUMBER = "number"
    DATE = "date"
    DATETIME = "datetime"
    STATUS = "status"


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: ColumnType = ColumnType.TEXT
    #: Shown unless an administrator has hidden it. Columns that are useful
    #: occasionally start hidden rather than being left out — the old reports
    #: were criticised for both extremes.
    default_visible: bool = True
    #: Summed into the report's footer. Only meaningful for money and number.
    total: bool = False


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    description: str
    columns: List[Column]
    #: Whether the report covers a range of days or a single day.
    single_day: bool = False
    #: A cashier may run this against their own till without holding
    #: hospital-wide finance rights; anyone else's till needs those.
    self_service: bool = False
    #: A clinical report names the permission it needs instead. The surgical
    #: register carries no money and is not finance's to gate.
    permission: Optional[str] = None
    #: Populated by the registry at import time.
    build: Optional[Callable[..., Any]] = field(default=None, compare=False)


REGISTRY: Dict[str, ReportSpec] = {}


def register(spec: ReportSpec, build: Callable[..., Any]) -> ReportSpec:
    stored = ReportSpec(
        key=spec.key,
        title=spec.title,
        description=spec.description,
        columns=spec.columns,
        single_day=spec.single_day,
        self_service=spec.self_service,
        permission=spec.permission,
        build=build,
    )
    REGISTRY[spec.key] = stored
    return stored


def get(key: str) -> Optional[ReportSpec]:
    return REGISTRY.get(key)


def catalogue() -> List[ReportSpec]:
    return list(REGISTRY.values())
