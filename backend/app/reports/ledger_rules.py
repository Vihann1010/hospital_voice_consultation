"""Arithmetic shared by the accounts reports, kept pure so it is tested directly.

Both functions exist to make a disagreement visible rather than to hide it: a
wallet whose movements do not add up to its recorded balance is flagged, and a
ledger carries its opening balance forward instead of starting every range at
zero.
"""
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence

WALLET_KINDS = ("deposit", "refund_credit", "applied", "withdrawal", "adjustment")
DOES_NOT_ADD_UP = "Does not add up"


def wallet_row(
    before: Sequence[Dict[str, Any]], within: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """One patient's wallet over a range.

    Entries carry kind, amount_paise (signed as stored) and balance_after_paise,
    in the order they were written. Opening and closing come from the stored
    running balance; the movements between are summed, and if the two do not
    agree the row says so.
    """
    opening = before[-1]["balance_after_paise"] if before else 0
    sums = {kind: 0 for kind in WALLET_KINDS}
    for entry in within:
        sums[entry["kind"]] = sums.get(entry["kind"], 0) + int(entry["amount_paise"])
    closing = within[-1]["balance_after_paise"] if within else opening
    moved = sum(sums.values())
    return {
        "opening_paise": opening,
        "deposits_paise": sums["deposit"],
        "refund_credits_paise": sums["refund_credit"],
        "applied_paise": abs(sums["applied"]),
        "withdrawn_paise": abs(sums["withdrawal"]),
        "adjustments_paise": sums["adjustment"],
        "closing_paise": closing,
        "check": "" if opening + moved == closing else DOES_NOT_ADD_UP,
    }


def running_ledger(
    movements: Iterable[Dict[str, Any]], *, date_from: date
) -> List[Dict[str, Any]]:
    """Rows for one account with a running balance.

    Each movement has on (date), particulars, debit_paise, credit_paise and an
    optional order key for movements on the same day. Movements before
    date_from are folded into one opening row, which appears only when there
    were any.
    """
    ordered = sorted(movements, key=lambda m: (m["on"], m.get("order", 0)))
    balance = 0
    rows: List[Dict[str, Any]] = []
    earlier = [m for m in ordered if m["on"] < date_from]
    if earlier:
        balance = sum(m["debit_paise"] - m["credit_paise"] for m in earlier)
        rows.append({"on": date_from, "particulars": "Opening balance",
                     "debit_paise": 0, "credit_paise": 0, "balance_paise": balance})
    for movement in ordered:
        if movement["on"] < date_from:
            continue
        balance += movement["debit_paise"] - movement["credit_paise"]
        rows.append({"on": movement["on"], "particulars": movement["particulars"],
                     "debit_paise": movement["debit_paise"], "credit_paise": movement["credit_paise"],
                     "balance_paise": balance})
    return rows


def closing_balance(rows: Sequence[Dict[str, Any]]) -> Optional[int]:
    return rows[-1]["balance_paise"] if rows else None
