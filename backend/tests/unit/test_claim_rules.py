"""How a TPA claim may move, and what it still owes."""
import pytest

from app.insurance import rules
from app.insurance.rules import ClaimRuleError, ageing_bucket, check_booking, check_move, check_settlement, settled_total

pytestmark = pytest.mark.unit


def figures(**extra):
    base = {"pre_auth_requested": 0, "pre_auth_approved": 0, "claimed": 0, "approved": 0, "booked": 0}
    base.update(extra)
    return base


def test_the_cashless_path_is_allowed():
    check_move(rules.DRAFT, rules.PRE_AUTH_REQUESTED, figures(pre_auth_requested=5000000))
    check_move(rules.PRE_AUTH_REQUESTED, rules.PRE_AUTH_APPROVED,
               figures(pre_auth_requested=5000000, pre_auth_approved=4000000))
    check_move(rules.PRE_AUTH_APPROVED, rules.SUBMITTED, figures(claimed=6200000))
    check_move(rules.SUBMITTED, rules.QUERIED, figures(claimed=6200000), query="Send the implant sticker")
    check_move(rules.QUERIED, rules.SUBMITTED, figures(claimed=6200000))
    check_move(rules.SUBMITTED, rules.PARTIALLY_APPROVED, figures(claimed=6200000, approved=5800000))


def test_reimbursement_goes_straight_to_submission():
    check_move(rules.DRAFT, rules.SUBMITTED, figures(claimed=100000))


@pytest.mark.parametrize("current,target", [
    (rules.DRAFT, rules.APPROVED),
    (rules.PRE_AUTH_REJECTED, rules.SUBMITTED),
    (rules.SUBMITTED, rules.PRE_AUTH_APPROVED),
    (rules.SETTLED, rules.SUBMITTED),
])
def test_moves_that_skip_a_step_are_refused(current, target):
    with pytest.raises(ClaimRuleError):
        check_move(current, target, figures(claimed=100, approved=100, pre_auth_requested=100, pre_auth_approved=100),
                   reason="x", query="x")


def test_settled_is_only_reached_by_recording_money():
    with pytest.raises(ClaimRuleError, match="recording the payer"):
        check_move(rules.APPROVED, rules.SETTLED, figures(claimed=100, approved=100))


def test_each_stage_needs_its_amount_or_reason():
    with pytest.raises(ClaimRuleError, match="asked for"):
        check_move(rules.DRAFT, rules.PRE_AUTH_REQUESTED, figures())
    with pytest.raises(ClaimRuleError, match="more than was asked"):
        check_move(rules.PRE_AUTH_REQUESTED, rules.PRE_AUTH_APPROVED,
                   figures(pre_auth_requested=100, pre_auth_approved=200))
    with pytest.raises(ClaimRuleError, match="amount claimed"):
        check_move(rules.DRAFT, rules.SUBMITTED, figures())
    with pytest.raises(ClaimRuleError, match="reason"):
        check_move(rules.SUBMITTED, rules.REJECTED, figures(claimed=100), reason="  ")
    with pytest.raises(ClaimRuleError, match="asked"):
        check_move(rules.SUBMITTED, rules.QUERIED, figures(claimed=100))


def test_full_and_partial_approval_are_kept_apart():
    with pytest.raises(ClaimRuleError, match="partially approved"):
        check_move(rules.SUBMITTED, rules.APPROVED, figures(claimed=1000, approved=900))
    with pytest.raises(ClaimRuleError, match="less than the amount claimed"):
        check_move(rules.SUBMITTED, rules.PARTIALLY_APPROVED, figures(claimed=1000, approved=1000))
    check_move(rules.SUBMITTED, rules.APPROVED, figures(claimed=1000, approved=1000))


def test_an_approved_claim_reopens_only_while_nothing_is_on_the_bill():
    check_move(rules.APPROVED, rules.SUBMITTED, figures(claimed=1000, approved=1000))
    with pytest.raises(ClaimRuleError, match="Remove it from the bill"):
        check_move(rules.APPROVED, rules.SUBMITTED, figures(claimed=1000, approved=1000, booked=1000))


def test_booking_the_payer_share_to_the_bill():
    check_booking(status=rules.APPROVED, approved=5000, booked=0, amount=5000, bill_balance=7000)
    with pytest.raises(ClaimRuleError, match="approved claim"):
        check_booking(status=rules.SUBMITTED, approved=5000, booked=0, amount=5000, bill_balance=7000)
    with pytest.raises(ClaimRuleError, match="already on the bill"):
        check_booking(status=rules.APPROVED, approved=5000, booked=5000, amount=1, bill_balance=7000)
    with pytest.raises(ClaimRuleError, match="more than the payer approved"):
        check_booking(status=rules.APPROVED, approved=5000, booked=0, amount=5001, bill_balance=7000)
    with pytest.raises(ClaimRuleError, match="still owed on the bill"):
        check_booking(status=rules.APPROVED, approved=5000, booked=0, amount=5000, bill_balance=4000)
    with pytest.raises(ClaimRuleError, match="more than zero"):
        check_booking(status=rules.APPROVED, approved=5000, booked=0, amount=0, bill_balance=4000)


def test_settlements_account_for_received_tds_and_disallowed():
    live = [{"received": 45000, "tds": 5000, "deduction": 0},
            {"received": 10000, "tds": 0, "deduction": 0, "cancelled": True}]
    assert settled_total(live) == 50000
    check_settlement(booked=60000, already_settled=50000, received=0, tds=0, deduction=10000,
                     deduction_reason="Room rent over the policy limit", mode="net_banking")
    with pytest.raises(ClaimRuleError, match="only 100.00 is still owed"):
        check_settlement(booked=60000, already_settled=50000, received=10001, tds=0, deduction=0,
                         deduction_reason=None, mode="net_banking")
    with pytest.raises(ClaimRuleError, match="why the payer disallowed"):
        check_settlement(booked=60000, already_settled=0, received=50000, tds=0, deduction=10000,
                         deduction_reason="", mode="cheque")
    with pytest.raises(ClaimRuleError, match="on the bill before"):
        check_settlement(booked=0, already_settled=0, received=1, tds=0, deduction=0, deduction_reason=None,
                         mode="upi")
    with pytest.raises(ClaimRuleError, match="bank transfer"):
        check_settlement(booked=100, already_settled=0, received=100, tds=0, deduction=0, deduction_reason=None,
                         mode="cash")
    with pytest.raises(ClaimRuleError, match="Enter what"):
        check_settlement(booked=100, already_settled=0, received=0, tds=0, deduction=0, deduction_reason=None,
                         mode="upi")
    with pytest.raises(ClaimRuleError, match="negative"):
        check_settlement(booked=100, already_settled=0, received=150, tds=-50, deduction=0, deduction_reason=None,
                         mode="upi")


@pytest.mark.parametrize("days,bucket", [(0, "0-30 days"), (30, "0-30 days"), (31, "31-60 days"),
                                         (90, "61-90 days"), (180, "91-180 days"), (181, "Over 180 days")])
def test_ageing(days, bucket):
    assert ageing_bucket(days) == bucket
