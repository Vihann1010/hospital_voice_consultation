"""The Indian financial year, as a first-class context.

April to March. A bill raised on 31 March and one raised on 1 April belong to
different years and to different numbering series, so almost every report,
ledger and document number in the system is scoped by one — which is why the
old system made choosing a year part of signing in rather than a filter buried
on each report.

The label form is the one staff say out loud and see on invoices: "26-27".
"""
from datetime import date
from typing import List, NamedTuple, Optional
from app.core.clock import local_today

# The hospital did not exist before this, so there is no year to offer earlier.
# Anything imported from the old system that predates it is still stored with
# its own year label; this only bounds what the picker offers.
EARLIEST_YEAR = 2015


class FinancialYear(NamedTuple):
    label: str          # "26-27"
    start_year: int     # 2026
    start: date         # 2026-04-01
    end: date           # 2027-03-31

    @property
    def is_current(self) -> bool:
        return self.start <= local_today() <= self.end

    def contains(self, when: date) -> bool:
        return self.start <= when <= self.end


def start_year_for(on: Optional[date] = None) -> int:
    """Which April the given date belongs to."""
    today = on or local_today()
    return today.year if today.month >= 4 else today.year - 1


def label_for(on: Optional[date] = None) -> str:
    """The financial year label a date falls in, e.g. "26-27"."""
    start = start_year_for(on)
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def from_start_year(start_year: int) -> FinancialYear:
    return FinancialYear(
        label=f"{start_year % 100:02d}-{(start_year + 1) % 100:02d}",
        start_year=start_year,
        start=date(start_year, 4, 1),
        end=date(start_year + 1, 3, 31),
    )


def parse(label: str) -> Optional[FinancialYear]:
    """Turn "26-27" back into a year, or None if it is not one.

    Rejects mismatched halves — "26-28" is not a financial year, and silently
    accepting it would scope a report to a range nobody asked for.
    """
    parts = (label or "").strip().split("-")
    if len(parts) != 2 or not all(p.isdigit() and len(p) == 2 for p in parts):
        return None
    first, second = int(parts[0]), int(parts[1])
    if (first + 1) % 100 != second:
        return None
    start_year = 2000 + first
    if not EARLIEST_YEAR <= start_year <= local_today().year + 1:
        return None
    return from_start_year(start_year)


def current() -> FinancialYear:
    return from_start_year(start_year_for())


def selectable(on: Optional[date] = None) -> List[FinancialYear]:
    """Years the hospital may work in, newest first.

    The current year and every year back to the earliest, plus nothing in the
    future: a receipt cannot be raised in a year that has not started.
    """
    latest = start_year_for(on)
    return [from_start_year(y) for y in range(latest, EARLIEST_YEAR - 1, -1)]


def resolve(label: Optional[str]) -> FinancialYear:
    """The year a request is working in — the one asked for, else the current one."""
    if not label:
        return current()
    year = parse(label)
    return year or current()
