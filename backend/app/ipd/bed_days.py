"""Bed-day accrual.

The single most error-prone calculation in inpatient billing, and the one a
hospital notices last: a bed charged twice on a transfer day, or a day missed
on discharge, is invisible on any one bill and adds up to real money across a
year.

The rule implemented here is the one Indian hospitals overwhelmingly use, and
it is stated explicitly because every hospital assumes theirs is obvious:

    Charging is by CALENDAR DAY, counting the day of admission and every
    subsequent calendar day the patient is still admitted at the charging
    hour. The day of discharge is charged only if the patient leaves after
    the hospital's discharge cut-off time.

That last clause is what stops a patient admitted at 11pm and discharged at
9am the next morning being billed two full days for ten hours in a bed.

On a transfer, the day belongs to whichever bed the patient occupied at the
charging hour — never both. A patient moved from a general ward to ICU at
noon is charged one day, at the ICU rate if the charging hour falls after the
move.

Everything here is pure: dates and rates in, charges out. No database, so
every boundary case is testable without a hospital.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Occupancy:
    """One continuous stay in one bed, at one rate."""

    bed_id: str
    bed_label: str
    ward_name: str
    rate_paise: int
    started_at: datetime
    ended_at: Optional[datetime] = None  # None means still occupying


@dataclass(frozen=True)
class BedDayCharge:
    on: date
    bed_id: str
    bed_label: str
    ward_name: str
    rate_paise: int


class BedDayError(Exception):
    pass


def _as_date(moment: datetime) -> date:
    return moment.date()


def occupancy_at(
    occupancies: Sequence[Occupancy], moment: datetime
) -> Optional[Occupancy]:
    """Which bed the patient held at a given instant.

    Later occupancies win on an exact boundary, so the moment of transfer
    belongs to the new bed rather than being ambiguous.
    """
    held: Optional[Occupancy] = None
    for occupancy in sorted(occupancies, key=lambda o: o.started_at):
        if occupancy.started_at > moment:
            continue
        if occupancy.ended_at is not None and occupancy.ended_at <= moment:
            continue
        held = occupancy
    return held


def compute_bed_days(
    occupancies: Sequence[Occupancy],
    *,
    admitted_at: datetime,
    discharged_at: Optional[datetime],
    charging_hour: int = 8,
    discharge_cutoff_hour: int = 12,
    up_to: Optional[datetime] = None,
    absences: Sequence[Tuple[datetime, Optional[datetime]]] = (),
) -> List[BedDayCharge]:
    """Every bed-day owed for a stay.

    `charging_hour` is the hour of the morning at which the day's bed is
    determined — a hospital's "census hour". `discharge_cutoff_hour` is the
    time after which the discharge day itself becomes chargeable.

    `up_to` bills an ongoing admission to a point in time, so a running total
    can be shown at the bedside before the patient leaves.
    """
    if not occupancies:
        raise BedDayError("A stay must have at least one bed occupancy.")
    if discharged_at is not None and discharged_at < admitted_at:
        raise BedDayError("Discharge cannot be before admission.")
    if not 0 <= charging_hour <= 23:
        raise BedDayError("charging_hour must be an hour of the day.")

    end_moment = discharged_at or up_to or datetime.now(tz=admitted_at.tzinfo)
    if end_moment < admitted_at:
        raise BedDayError("The billing period ends before admission.")

    charges: List[BedDayCharge] = []
    first_day = _as_date(admitted_at)
    last_day = _as_date(end_moment)

    current = first_day
    while current <= last_day:
        # The day of discharge is charged only if the patient stayed past the
        # cut-off. Ten hours overnight is one day, not two.
        if discharged_at is not None and current == _as_date(discharged_at):
            if current == first_day:
                # Admitted and discharged on the same calendar day: always one
                # day, however brief. A bed was taken out of service.
                pass
            elif discharged_at.hour < discharge_cutoff_hour:
                current += timedelta(days=1)
                continue

        # Which bed did the patient hold at the census hour? On the admission
        # day the census hour may already have passed, so fall back to the
        # admission moment itself.
        census = datetime.combine(current, time(hour=charging_hour),
                                  tzinfo=admitted_at.tzinfo)
        if census < admitted_at:
            census = admitted_at
        if discharged_at is not None and census > discharged_at:
            census = discharged_at

        # Away on leave with the bed given up: no bed was held for the patient,
        # so the day is not owed — not even to the bed they come back to.
        if any(begin <= census and (end is None or census < end) for begin, end in absences):
            current += timedelta(days=1)
            continue

        held = occupancy_at(occupancies, census)
        if held is None:
            # No bed at the census hour (a gap between transfers). Use the
            # occupancy that began soonest after it rather than skipping a
            # day the patient was demonstrably in hospital for.
            later = [o for o in occupancies if o.started_at >= census]
            if not later:
                current += timedelta(days=1)
                continue
            held = min(later, key=lambda o: o.started_at)

        charges.append(
            BedDayCharge(
                on=current,
                bed_id=held.bed_id,
                bed_label=held.bed_label,
                ward_name=held.ward_name,
                rate_paise=held.rate_paise,
            )
        )
        current += timedelta(days=1)

    return charges


def total_bed_charge_paise(charges: Sequence[BedDayCharge]) -> int:
    return sum(charge.rate_paise for charge in charges)
