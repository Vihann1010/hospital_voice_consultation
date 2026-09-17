"""TPA and insurance claims: what a claim may do next, and what it still owes.

Pure functions over plain values, so every rule is tested without a database.

A claim moves the way a cashless case moves at a TPA desk:

  draft -> pre-authorisation requested -> approved or rejected
  draft or pre-authorisation approved -> claim submitted (the final bill goes in)
  requested or submitted -> queried -> answered (back to where it was asked)
  submitted -> approved, partially approved or rejected
  rejected -> submitted again (an appeal)
  approved -> settled, only by recording the money the payer sent

Money is tracked in three steps, because the family and the insurer owe
different parts of one bill and the accountant has to see both:

* **Approved** is what the payer agreed to pay.
* **Booked** is the part put on the hospital bill as the payer's share. The
  family then owes only the rest, and the books move that amount from patients
  receivable to insurance receivable.
* **Settled** is what came back: money received, TDS the payer deducted, and
  any amount the payer disallowed. Until those add up to the booked amount,
  the difference is still owed by the payer.
"""
from typing import Dict, Iterable, Mapping, Optional

DRAFT = "draft"
PRE_AUTH_REQUESTED = "pre_auth_requested"
PRE_AUTH_APPROVED = "pre_auth_approved"
PRE_AUTH_REJECTED = "pre_auth_rejected"
SUBMITTED = "submitted"
QUERIED = "queried"
APPROVED = "approved"
PARTIALLY_APPROVED = "partially_approved"
REJECTED = "rejected"
SETTLED = "settled"

STATUS_LABEL = {
    DRAFT: "Draft",
    PRE_AUTH_REQUESTED: "Pre-authorisation requested",
    PRE_AUTH_APPROVED: "Pre-authorisation approved",
    PRE_AUTH_REJECTED: "Pre-authorisation rejected",
    SUBMITTED: "Claim submitted",
    QUERIED: "Query raised",
    APPROVED: "Approved",
    PARTIALLY_APPROVED: "Partially approved",
    REJECTED: "Rejected",
    SETTLED: "Settled",
}

# Where a claim may be moved by hand. Settled is absent on purpose: a claim is
# settled by recording the payer's money, never by changing a label.
TRANSITIONS: Dict[str, frozenset] = {
    DRAFT: frozenset({PRE_AUTH_REQUESTED, SUBMITTED}),
    PRE_AUTH_REQUESTED: frozenset({PRE_AUTH_APPROVED, PRE_AUTH_REJECTED, QUERIED}),
    # An approved pre-authorisation may be enhanced (asked again for more)
    # before the final bill is submitted.
    PRE_AUTH_APPROVED: frozenset({SUBMITTED, PRE_AUTH_REQUESTED}),
    PRE_AUTH_REJECTED: frozenset({PRE_AUTH_REQUESTED}),
    SUBMITTED: frozenset({QUERIED, APPROVED, PARTIALLY_APPROVED, REJECTED}),
    # A query is answered back to the stage it was raised at.
    QUERIED: frozenset({PRE_AUTH_REQUESTED, SUBMITTED}),
    # Reopened only while nothing is booked to the bill; see check_move.
    APPROVED: frozenset({SUBMITTED}),
    PARTIALLY_APPROVED: frozenset({SUBMITTED}),
    REJECTED: frozenset({SUBMITTED}),
    SETTLED: frozenset(),
}

BOOKABLE = frozenset({APPROVED, PARTIALLY_APPROVED})
# Claims the payer still has to act on or pay: the desk's working list.
OPEN = frozenset({DRAFT, PRE_AUTH_REQUESTED, PRE_AUTH_APPROVED, SUBMITTED, QUERIED, APPROVED, PARTIALLY_APPROVED})

SETTLEMENT_MODES = ("net_banking", "cheque", "upi")

AGEING_BUCKETS = ("0-30 days", "31-60 days", "61-90 days", "91-180 days", "Over 180 days")


class ClaimRuleError(ValueError):
    """A claim change that cannot be made as asked."""


def _money(label: str, value: Optional[int]) -> int:
    amount = int(value or 0)
    if amount < 0:
        raise ClaimRuleError(f"{label} cannot be negative.")
    return amount


def check_move(
    current: str,
    target: str,
    figures: Mapping[str, Optional[int]],
    *,
    reason: Optional[str] = None,
    query: Optional[str] = None,
) -> None:
    """Refuse a status change the claim cannot make, or one missing what it needs.

    `figures` holds the amounts as they will stand after the change:
    pre_auth_requested, pre_auth_approved, claimed, approved and booked.
    """
    if target == SETTLED:
        raise ClaimRuleError("A claim is settled by recording the payer's payment, not by changing its status.")
    if target not in TRANSITIONS:
        raise ClaimRuleError(f"{target} is not a claim status.")
    if target == current:
        raise ClaimRuleError(f"The claim is already {STATUS_LABEL[current].lower()}.")
    if target not in TRANSITIONS.get(current, frozenset()):
        raise ClaimRuleError(
            f"A claim that is {STATUS_LABEL[current].lower()} cannot be moved to {STATUS_LABEL[target].lower()}."
        )

    requested = _money("The amount requested", figures.get("pre_auth_requested"))
    pre_approved = _money("The pre-authorised amount", figures.get("pre_auth_approved"))
    claimed = _money("The claimed amount", figures.get("claimed"))
    approved = _money("The approved amount", figures.get("approved"))
    booked = _money("The booked amount", figures.get("booked"))

    if current in BOOKABLE and booked:
        raise ClaimRuleError("Part of this claim is on the bill. Remove it from the bill before reopening the claim.")
    if target == PRE_AUTH_REQUESTED and requested <= 0:
        raise ClaimRuleError("Enter the amount asked for in the pre-authorisation.")
    if target == PRE_AUTH_APPROVED:
        if pre_approved <= 0:
            raise ClaimRuleError("Enter the amount the payer pre-authorised.")
        if pre_approved > requested:
            raise ClaimRuleError("The pre-authorised amount is more than was asked for.")
    if target == SUBMITTED and claimed <= 0:
        raise ClaimRuleError("Enter the amount claimed.")
    if target == APPROVED and approved != claimed:
        raise ClaimRuleError(
            "Approved means the whole claimed amount. If the payer approved less, mark it partially approved."
        )
    if target == PARTIALLY_APPROVED and not 0 < approved < claimed:
        raise ClaimRuleError("A partial approval is more than nothing and less than the amount claimed.")
    if target in (APPROVED, PARTIALLY_APPROVED) and claimed <= 0:
        raise ClaimRuleError("Enter the amount claimed.")
    if target in (REJECTED, PRE_AUTH_REJECTED) and not (reason or "").strip():
        raise ClaimRuleError("Record the payer's reason for rejecting.")
    if target == QUERIED and not (query or "").strip():
        raise ClaimRuleError("Record what the payer asked.")


def check_booking(*, status: str, approved: int, booked: int, amount: int, bill_balance: int) -> None:
    """Put the payer's share on the bill."""
    if status not in BOOKABLE:
        raise ClaimRuleError("Only an approved claim can be put on the bill.")
    if booked:
        raise ClaimRuleError("This claim is already on the bill. Remove it first to book a different amount.")
    if amount <= 0:
        raise ClaimRuleError("The amount to put on the bill must be more than zero.")
    if amount > approved:
        raise ClaimRuleError("That is more than the payer approved.")
    if amount > bill_balance:
        raise ClaimRuleError("That is more than is still owed on the bill.")


def settled_total(settlements: Iterable[Mapping[str, int]]) -> int:
    """Received, TDS and disallowed together, for live settlements only."""
    return sum(
        int(s.get("received", 0)) + int(s.get("tds", 0)) + int(s.get("deduction", 0))
        for s in settlements
        if not s.get("cancelled")
    )


def check_settlement(
    *,
    booked: int,
    already_settled: int,
    received: int,
    tds: int,
    deduction: int,
    deduction_reason: Optional[str],
    mode: str,
) -> None:
    """A payment from the payer against the amount booked to the bill."""
    received = _money("The amount received", received)
    tds = _money("TDS", tds)
    deduction = _money("The disallowed amount", deduction)
    if booked <= 0:
        raise ClaimRuleError("Put the approved amount on the bill before recording the payer's payment.")
    if received + tds + deduction <= 0:
        raise ClaimRuleError("Enter what the payer paid, deducted as TDS, or disallowed.")
    if mode not in SETTLEMENT_MODES:
        raise ClaimRuleError("The payer pays by bank transfer, cheque or UPI.")
    if deduction and not (deduction_reason or "").strip():
        raise ClaimRuleError("Record why the payer disallowed part of the claim.")
    outstanding = booked - already_settled
    if received + tds + deduction > outstanding:
        raise ClaimRuleError(
            f"That accounts for {(received + tds + deduction) / 100:,.2f}, but only "
            f"{outstanding / 100:,.2f} is still owed by the payer."
        )


def ageing_bucket(days: int) -> str:
    if days <= 30:
        return AGEING_BUCKETS[0]
    if days <= 60:
        return AGEING_BUCKETS[1]
    if days <= 90:
        return AGEING_BUCKETS[2]
    if days <= 180:
        return AGEING_BUCKETS[3]
    return AGEING_BUCKETS[4]
