"""Wallet and ledger arithmetic behind the reconciliation reports."""
from datetime import date

import pytest

from app.reports.ledger_rules import DOES_NOT_ADD_UP, closing_balance, running_ledger, wallet_row

pytestmark = pytest.mark.unit


def entry(kind, amount, after):
    return {"kind": kind, "amount_paise": amount, "balance_after_paise": after}


def test_wallet_row_carries_opening_and_sums_movements():
    before = [entry("deposit", 50000, 50000), entry("applied", -20000, 30000)]
    within = [entry("deposit", 10000, 40000), entry("applied", -5000, 35000),
              entry("withdrawal", -15000, 20000), entry("refund_credit", 3000, 23000)]
    row = wallet_row(before, within)
    assert row == {
        "opening_paise": 30000, "deposits_paise": 10000, "refund_credits_paise": 3000,
        "applied_paise": 5000, "withdrawn_paise": 15000, "adjustments_paise": 0,
        "closing_paise": 23000, "check": "",
    }


def test_wallet_row_with_no_movement_in_range_keeps_the_opening():
    row = wallet_row([entry("deposit", 40000, 40000)], [])
    assert row["opening_paise"] == row["closing_paise"] == 40000 and row["check"] == ""


def test_wallet_row_flags_a_balance_that_does_not_add_up():
    row = wallet_row([], [entry("deposit", 10000, 10000), entry("applied", -2000, 9000)])
    assert row["check"] == DOES_NOT_ADD_UP


def test_ledger_folds_earlier_movements_into_an_opening_balance():
    movements = [
        {"on": date(2026, 9, 1), "particulars": "Advance", "debit_paise": 0, "credit_paise": 100000, "order": 0},
        {"on": date(2026, 9, 1), "particulars": "Bed", "debit_paise": 80000, "credit_paise": 0, "order": 1},
        {"on": date(2026, 9, 2), "particulars": "Bed", "debit_paise": 80000, "credit_paise": 0, "order": 1},
        {"on": date(2026, 9, 3), "particulars": "Payment", "debit_paise": 0, "credit_paise": 60000, "order": 3},
    ]
    rows = running_ledger(movements, date_from=date(2026, 9, 2))
    assert [(r["particulars"], r["balance_paise"]) for r in rows] == [
        ("Opening balance", -20000), ("Bed", 60000), ("Payment", 0)]
    assert closing_balance(rows) == 0


def test_ledger_without_earlier_movements_has_no_opening_row():
    rows = running_ledger([{"on": date(2026, 9, 5), "particulars": "Bed", "debit_paise": 1, "credit_paise": 0}],
                          date_from=date(2026, 9, 1))
    assert [r["particulars"] for r in rows] == ["Bed"]


def test_same_day_movements_follow_their_order_key():
    movements = [
        {"on": date(2026, 9, 1), "particulars": "Bed", "debit_paise": 500, "credit_paise": 0, "order": 1},
        {"on": date(2026, 9, 1), "particulars": "Advance", "debit_paise": 0, "credit_paise": 1000, "order": 0},
    ]
    assert [r["balance_paise"] for r in running_ledger(movements, date_from=date(2026, 9, 1))] == [-1000, -500]
