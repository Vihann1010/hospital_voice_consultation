"""Consultant payout arithmetic."""
import pytest

from app.accounts.payout import eligible_amount, refund_clawback, settlement, share, validate_terms

pytestmark = pytest.mark.unit

LINES = [{"category": "consultation", "taxable": 50000}, {"category": "procedure", "taxable": 30000},
         {"category": None, "taxable": 20000}]


def test_only_the_agreed_kinds_of_service_count():
    assert eligible_amount(LINES, 100000, ["consultation"]) == 50000
    assert eligible_amount(LINES, 100000, ["consultation", "procedure"]) == 80000
    assert eligible_amount(LINES, 100000, ["other"]) == 20000


def test_a_bill_level_discount_is_shared_in_proportion():
    # Rs 1,000 of lines, billed at Rs 900: the consultation's Rs 500 carries Rs 50 of the discount.
    assert eligible_amount(LINES, 90000, ["consultation"]) == 45000


def test_nothing_billed_is_nothing_eligible():
    assert eligible_amount([], 0, ["consultation"]) == 0
    assert eligible_amount([{"category": "consultation", "taxable": 0}], 0, ["consultation"]) == 0


def test_share_rounds_half_up_and_keeps_sign():
    assert share(50000, 30) == 15000
    assert share(333, 50) == 167
    assert share(-333, 50) == -167
    assert share(0, 40) == 0


@pytest.mark.parametrize("total, paid, state", [(1000, 1000, "settled"), (1000, 1200, "settled"),
                                                (1000, 400, "part_paid"), (1000, 0, "unpaid"), (0, 0, "nothing")])
def test_settlement(total, paid, state):
    assert settlement(total, paid) == state


def test_a_refund_after_payout_claws_back_in_proportion():
    # A Rs 1,000 bill with Rs 500 eligible at 40%: refunding Rs 200 claws back Rs 100 of base, Rs 40 of share.
    assert refund_clawback(20000, 100000, 50000, 40) == {"base_paise": -10000, "share_paise": -4000}
    assert refund_clawback(200000, 100000, 50000, 40) == {"base_paise": -50000, "share_paise": -20000}
    assert refund_clawback(20000, 100000, 0, 40) == {"base_paise": 0, "share_paise": 0}


def test_terms_validation():
    assert validate_terms(30, ["consultation"]) is None
    assert validate_terms(0, []) is None
    assert "between 0 and 100" in validate_terms(101, ["consultation"])
    assert "at least one" in validate_terms(20, [])
    assert "Unknown" in validate_terms(20, ["surgery"])
