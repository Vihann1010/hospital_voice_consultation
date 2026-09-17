"""The hospital's wall clock.

Stored timestamps are UTC and stay UTC — that is not negotiable, because a
timezone-naive database cannot survive a daylight-saving change or a server
move. But almost every question the front desk asks is a local one: which
patients came in *today*, is nine o'clock free, does this receipt fall in
today's closing.

Answering those from the server's clock is wrong twice over. The container
runs on UTC, so between midnight and 05:30 IST `date.today()` returns
yesterday; and a workstation's own clock is not a source of truth at all.
Both questions resolve here instead, against the configured hospital
timezone, so there is one answer and one place to change it.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def zone() -> ZoneInfo:
    return ZoneInfo(settings.HOSPITAL_TIMEZONE)


def local_now() -> datetime:
    """Now, as the hospital's clock on the wall shows it."""
    return datetime.now(zone())


def local_today() -> date:
    """The hospital's current date — not the server's."""
    return local_now().date()


def to_local(moment: datetime) -> datetime:
    """Render a stored timestamp in hospital time.

    A naive value is read as UTC rather than as local: everything this
    application writes is UTC, so guessing local would shift genuine
    timestamps by five and a half hours.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone())


def local_datetime(on: date, at: time) -> datetime:
    """Combine a local date and a local time into an aware timestamp."""
    return datetime.combine(on, at, tzinfo=zone())


def day_bounds(on: date) -> tuple[datetime, datetime]:
    """The UTC half-open interval [start, end) covering one local day.

    Used for every "what happened today" query: comparing a UTC column
    against a bare date would slice the day at 05:30 in the morning.
    """
    start = local_datetime(on, time.min)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)
