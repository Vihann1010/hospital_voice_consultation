"""The rules of the inpatient drug chart, with no database in them.

When a dose is due, whether it can be signed yet, and whether it has been
missed. Kept apart from the service so the arithmetic — which is where the
chart went wrong — can be tested directly.

Three things the chart previously got wrong, each of which this module now
decides:

* **Round times are hospital time.** A dose written "08:00" was scheduled at
  08:00 UTC, which is 13:30 on the ward. Every time here is interpreted in the
  hospital's timezone and stored in UTC.
* **A frequency means something.** An order written "BD" with no explicit
  times used to schedule nothing at all, so nothing ever showed as due. Each
  frequency has default round times, overridable per order.
* **The chart keeps going.** Doses were laid out for 48 hours at the moment of
  prescribing and never again, so a five-day course went blank on day three.
  The schedule is topped up whenever the chart is read, including back-filling
  a gap — a dose that was due while nobody opened the chart is shown as
  overdue, not silently absent.
"""
from datetime import datetime, time, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from app.core.clock import local_datetime, to_local

# Default round times per frequency, in hospital time. A ward's own drug round
# may differ; any order can give explicit times instead.
FREQUENCY_TIMES: Dict[str, List[str]] = {
    "OD": ["08:00"],
    "BD": ["08:00", "20:00"],
    "TDS": ["08:00", "14:00", "20:00"],
    "QID": ["06:00", "12:00", "18:00", "22:00"],
    "HS": ["21:00"],
    "Q4H": ["02:00", "06:00", "10:00", "14:00", "18:00", "22:00"],
    "Q6H": ["00:00", "06:00", "12:00", "18:00"],
    "Q8H": ["06:00", "14:00", "22:00"],
    "Q12H": ["08:00", "20:00"],
    "STAT": [],
    "SOS": [],
}

# Synonyms written on Indian drug charts, resolved to the codes above.
_ALIASES = {"TID": "TDS", "QDS": "QID", "BID": "BD", "PRN": "SOS", "ONCE": "STAT"}

AS_NEEDED = frozenset({"SOS"})
ONCE = frozenset({"STAT"})

# How far ahead doses are laid out, and how far back a gap is filled.
SCHEDULE_HORIZON = timedelta(hours=36)
MAX_BACKFILL = timedelta(days=7)

# A dose may be signed from an hour before it is due — a drug round does not
# start on the minute — and is overdue an hour after.
SIGN_EARLY = timedelta(minutes=60)
OVERDUE_AFTER = timedelta(minutes=60)


class ScheduleError(ValueError):
    """An order whose schedule cannot be worked out, with a reason to show."""


def normalise_frequency(code: Optional[str]) -> str:
    cleaned = (code or "").strip().upper().replace(" ", "").replace(".", "")
    return _ALIASES.get(cleaned, cleaned)


def parse_clock(value: object) -> Optional[time]:
    """"08:00" -> time(8, 0). Anything unreadable is None, not an exception."""
    try:
        hour, minute = str(value).strip().split(":")[:2]
        return time(int(hour), int(minute))
    except (ValueError, TypeError):
        return None


def clock_times(frequency: Optional[str], explicit: Iterable[str] = ()) -> List[time]:
    """The times of day this order is due. Empty for STAT and SOS."""
    code = normalise_frequency(frequency)
    if code in AS_NEEDED or code in ONCE:
        return []
    parsed = sorted({moment for moment in (parse_clock(v) for v in explicit or []) if moment})
    if parsed:
        return parsed
    defaults = FREQUENCY_TIMES.get(code)
    if defaults:
        return [parse_clock(value) for value in defaults]
    raise ScheduleError(
        f"There are no standard round times for {frequency!r}. "
        "Enter the times this medicine is due."
    )


def due_moments(times: List[time], *, start: datetime, until: datetime) -> List[datetime]:
    """Every due moment, in UTC, falling in [start, until)."""
    if not times or until <= start:
        return []
    moments: List[datetime] = []
    day = to_local(start).date()
    last = to_local(until).date()
    while day <= last:
        for at in times:
            moment = local_datetime(day, at).astimezone(timezone.utc)
            if start <= moment < until:
                moments.append(moment)
        day += timedelta(days=1)
    return sorted(moments)


def dose_state(*, due_at: datetime, was_given: Optional[bool], now: datetime) -> str:
    """given | omitted | overdue | due | upcoming."""
    if was_given is True:
        return "given"
    if was_given is False:
        return "omitted"
    if now > due_at + OVERDUE_AFTER:
        return "overdue"
    if now >= due_at - SIGN_EARLY:
        return "due"
    return "upcoming"


def can_sign(*, due_at: datetime, was_given: Optional[bool], now: datetime) -> bool:
    """A dose is signed once, and not before its window opens."""
    return was_given is None and now >= due_at - SIGN_EARLY
