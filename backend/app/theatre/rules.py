"""Operation theatre rules, with no database in them.

What order the theatre times must come in, how long a case took, whether two
cases collide in one room, and which way a case may move through its states.
Kept apart from the service so each rule can be tested on its own.

The theatre times are the legal record of what happened to a patient under
anaesthesia, and the surgical register is audited against them. So they are
checked the way a register clerk would check them: an incision cannot precede
the patient arriving in theatre, closure cannot precede incision, and nothing
can be recorded as having happened in the future.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# The milestones of one case, in the order they happen.
MILESTONES: Tuple[str, ...] = (
    "wheel_in_at",
    "anaesthesia_start_at",
    "incision_at",
    "closure_at",
    "wheel_out_at",
)

MILESTONE_LABEL: Dict[str, str] = {
    "wheel_in_at": "Wheeled in",
    "anaesthesia_start_at": "Anaesthesia started",
    "incision_at": "Incision",
    "closure_at": "Closure",
    "wheel_out_at": "Wheeled out",
}

# What must already be recorded before a milestone can be.
_REQUIRES: Dict[str, Tuple[str, ...]] = {
    "wheel_in_at": (),
    "anaesthesia_start_at": ("wheel_in_at",),
    "incision_at": ("wheel_in_at",),
    "closure_at": ("incision_at",),
    "wheel_out_at": ("wheel_in_at",),
}

ANAESTHESIA_TYPES: List[str] = [
    "General",
    "Spinal",
    "Epidural",
    "Combined spinal-epidural",
    "Regional block",
    "Local",
    "Sedation",
]

# Laterality is never optional on a booking. "Not applicable" is a statement
# someone made, not a blank nobody filled in — wrong-side surgery starts with
# a blank.
LATERALITY: List[str] = ["Left", "Right", "Bilateral", "Not applicable"]

PRIORITIES: List[str] = ["elective", "emergency"]

GRADES: List[str] = ["minor", "intermediate", "major", "super major"]

# Workstation clocks drift; a time a few minutes ahead is a clock, not a lie.
CLOCK_SKEW = timedelta(minutes=5)


class TheatreRuleError(ValueError):
    """A theatre action that breaks a rule, with a reason to show."""


# ------------------------------------------------------------------ status
_TRANSITIONS: Dict[Tuple[str, str], str] = {
    ("scheduled", "wheel_in"): "in_theatre",
    ("in_theatre", "wheel_out"): "completed",
    ("scheduled", "cancel"): "cancelled",
}


def next_status(current: str, event: str) -> str:
    """The state a case moves to, or an error saying why it cannot."""
    target = _TRANSITIONS.get((current, event))
    if target is not None:
        return target
    if event == "cancel" and current == "in_theatre":
        raise TheatreRuleError(
            "A patient already in theatre cannot be cancelled. Record what happened and "
            "wheel them out."
        )
    if event == "wheel_in" and current == "in_theatre":
        raise TheatreRuleError("This patient is already in theatre.")
    if current in ("completed", "cancelled"):
        raise TheatreRuleError(f"This case is {current} and cannot be changed.")
    if event == "wheel_out" and current == "scheduled":
        raise TheatreRuleError("The patient has not been wheeled in yet.")
    raise TheatreRuleError(f"A case that is {current} cannot be moved by {event}.")


# --------------------------------------------------------------- milestones
def check_milestone(
    times: Dict[str, Optional[datetime]],
    key: str,
    value: datetime,
    *,
    now: datetime,
) -> Dict[str, Optional[datetime]]:
    """Record one milestone, or explain why it cannot be recorded.

    Returns the full set of times with the new one in place.
    """
    if key not in MILESTONES:
        raise TheatreRuleError(f"Unknown theatre time {key!r}.")
    if value > now + CLOCK_SKEW:
        raise TheatreRuleError(f"{MILESTONE_LABEL[key]} cannot be recorded in the future.")

    for needed in _REQUIRES[key]:
        if times.get(needed) is None:
            raise TheatreRuleError(
                f"Record {MILESTONE_LABEL[needed].lower()} before {MILESTONE_LABEL[key].lower()}."
            )

    position = MILESTONES.index(key)
    for earlier in MILESTONES[:position]:
        moment = times.get(earlier)
        if moment is not None and value < moment:
            raise TheatreRuleError(
                f"{MILESTONE_LABEL[key]} cannot be before {MILESTONE_LABEL[earlier].lower()} "
                f"({moment:%H:%M})."
            )
    for later in MILESTONES[position + 1:]:
        moment = times.get(later)
        if moment is not None and value > moment:
            raise TheatreRuleError(
                f"{MILESTONE_LABEL[key]} cannot be after {MILESTONE_LABEL[later].lower()} "
                f"({moment:%H:%M})."
            )

    if key == "wheel_out_at" and times.get("incision_at") is not None and times.get("closure_at") is None:
        raise TheatreRuleError(
            "An incision is recorded without a closure. Record closure before wheeling out."
        )

    updated = dict(times)
    updated[key] = value
    return updated


def _minutes(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
    if start is None or end is None or end < start:
        return None
    return int((end - start).total_seconds() // 60)


def durations(times: Dict[str, Optional[datetime]]) -> Dict[str, Optional[int]]:
    """How long the patient was in theatre, under the knife, and anaesthetised."""
    return {
        "theatre_minutes": _minutes(times.get("wheel_in_at"), times.get("wheel_out_at")),
        "surgery_minutes": _minutes(times.get("incision_at"), times.get("closure_at")),
        "anaesthesia_minutes": _minutes(times.get("anaesthesia_start_at"), times.get("wheel_out_at")),
    }


# ------------------------------------------------------------------ rooms
@dataclass(frozen=True)
class Booking:
    reference: str
    starts_at: datetime
    minutes: int


def clashes(new: Booking, others: List[Booking]) -> List[Booking]:
    """Bookings in the same room whose time overlaps the new one.

    Back-to-back cases — one ending exactly when the next begins — do not
    clash.
    """
    new_end = new.starts_at + timedelta(minutes=max(new.minutes, 1))
    found = []
    for other in others:
        if other.reference == new.reference:
            continue
        other_end = other.starts_at + timedelta(minutes=max(other.minutes, 1))
        if new.starts_at < other_end and other.starts_at < new_end:
            found.append(other)
    return found
