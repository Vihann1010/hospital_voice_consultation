"""Consultant payout arithmetic, kept pure so every rule is tested directly.

* **What counts.** A consultant earns a share of the lines on their bills in the
  categories agreed with them — by default consultations only. Tax is not
  shared; the share is on the taxable value.
* **A bill-level discount is shared.** When a bill was discounted as a whole,
  each eligible line carries its proportion of that discount.
* **Only settled bills.** A bill is paid out once it is fully paid. A bill
  still owed waits for a later run, and once counted it is locked.
* **A refund after payout is clawed back.** A refund on a bill already paid
  out appears as a negative line on the consultant's next payout, in the same
  proportion as the original share.
* Whole paise, rounded half up.
"""
from typing import Dict, Iterable, Optional

CATEGORIES = ("consultation", "procedure", "investigation", "registration", "other")


def eligible_amount(lines: Iterable[Dict], invoice_taxable: int, categories: Iterable[str]) -> int:
    """The part of a bill's taxable value the consultant's share is taken on."""
    lines = list(lines)
    wanted = set(categories)
    lines_taxable = sum(int(line["taxable"]) for line in lines)
    if lines_taxable <= 0:
        return 0
    eligible = sum(int(line["taxable"]) for line in lines
                   if (line.get("category") or "other") in wanted)
    if invoice_taxable >= lines_taxable:
        return eligible
    return eligible * max(invoice_taxable, 0) // lines_taxable


def share(base: int, percent: int) -> int:
    """percent of base in whole paise, rounded half up, keeping the sign."""
    if base < 0:
        return -share(-base, percent)
    return (base * percent + 50) // 100


def settlement(total: int, paid: int) -> str:
    if total <= 0:
        return "nothing"
    if paid >= total:
        return "settled"
    if paid <= 0:
        return "unpaid"
    return "part_paid"


WAITING_REASON = {
    "unpaid": "Not paid yet",
    "part_paid": "Only part paid",
    "nothing": "Nothing billed",
}


def refund_clawback(refund: int, invoice_total: int, eligible: int, percent: int) -> Dict[str, int]:
    """The negative base and share for a refund on a bill already paid out."""
    if invoice_total <= 0 or eligible <= 0 or refund <= 0:
        return {"base_paise": 0, "share_paise": 0}
    base = -(min(refund, invoice_total) * eligible // invoice_total)
    return {"base_paise": base, "share_paise": share(base, percent)}


def validate_terms(percent: int, categories: Iterable[str]) -> Optional[str]:
    chosen = list(categories)
    if not 0 <= percent <= 100:
        return "The share must be between 0 and 100 percent."
    if percent > 0 and not chosen:
        return "Choose at least one kind of service the share applies to."
    unknown = [c for c in chosen if c not in CATEGORIES]
    if unknown:
        return f"Unknown service kind: {', '.join(unknown)}."
    return None
