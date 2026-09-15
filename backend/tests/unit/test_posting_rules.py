"""What each counter record means in the books."""
from datetime import date

import pytest

from app.accounts import chart
from app.accounts.posting import (
    Draft,
    Line,
    PostingError,
    check_balanced,
    invoice_draft,
    legacy_advance_draft,
    merge,
    payment_draft,
    settlement_draft,
    wallet_draft,
)

pytestmark = pytest.mark.unit

ON = date(2026, 9, 14)


def lines(draft):
    return sorted((line.ledger, line.debit, line.credit) for line in draft.lines)


def bill(**extra):
    base = {"number": "SAT/26-27/000001", "status": "issued", "issued_on": ON, "gross": 70000, "discount": 5000,
            "tax": 0, "total": 65000, "source": "OPD", "patient_name": "Asha",
            "lines": [{"category": "consultation", "gross": 50000}, {"category": "procedure", "gross": 20000}]}
    base.update(extra)
    return base


def test_every_system_ledger_sits_in_a_known_group():
    codes = {code for code, *_ in chart.GROUPS}
    assert all(group in codes for *_, group in chart.LEDGERS)
    keys = [key for key, *_ in chart.LEDGERS]
    assert len(keys) == len(set(keys))


def test_a_bill_debits_the_patient_and_credits_income_by_kind():
    draft = invoice_draft(bill())
    assert draft.voucher_type == "sales"
    assert lines(draft) == sorted([("patient_debtors", 65000, 0), ("discount_allowed", 5000, 0),
                                   ("income_consultation", 0, 50000), ("income_procedure", 0, 20000)])


def test_inpatient_and_lab_bills_go_to_their_own_income():
    assert lines(invoice_draft(bill(source="IPD", discount=0, total=70000))) == sorted(
        [("patient_debtors", 70000, 0), ("income_ipd", 0, 70000)])
    assert ("income_lab", 0, 70000) in lines(invoice_draft(bill(source="Lab", discount=0, total=70000)))


def test_tax_is_credited_to_gst_output():
    draft = invoice_draft(bill(discount=0, tax=1800, total=71800))
    assert ("gst_output", 0, 1800) in lines(draft)


def test_cancelled_and_draft_bills_post_nothing():
    assert invoice_draft(bill(status="cancelled")) is None
    assert invoice_draft(bill(issued_on=None)) is None


@pytest.mark.parametrize("change", [{"total": 64000}, {"lines": [{"category": "consultation", "gross": 50000}]}])
def test_a_bill_that_does_not_add_up_is_refused(change):
    with pytest.raises(PostingError):
        invoice_draft(bill(**change))


def test_receipts_and_refunds_by_mode():
    receipt = payment_draft({"receipt_number": "RCP/1", "invoice_number": "SAT/1", "mode": "upi",
                             "is_refund": False, "amount": 30000, "on": ON})
    assert receipt.voucher_type == "receipt"
    assert lines(receipt) == sorted([("bank_upi", 30000, 0), ("patient_debtors", 0, 30000)])
    refund = payment_draft({"receipt_number": "RCP/2", "invoice_number": "SAT/1", "mode": "cash",
                            "is_refund": True, "amount": -10000, "on": ON})
    assert refund.voucher_type == "payment"
    assert lines(refund) == sorted([("patient_debtors", 10000, 0), ("cash", 0, 10000)])


def test_settling_from_the_wallet_moves_advances_not_cash():
    draft = payment_draft({"receipt_number": "RCP/3", "invoice_number": "SAT/1", "mode": "wallet",
                           "is_refund": False, "amount": 20000, "on": ON})
    assert draft.voucher_type == "journal"
    assert lines(draft) == sorted([("patient_advances", 20000, 0), ("patient_debtors", 0, 20000)])
    to_wallet = payment_draft({"receipt_number": "RCP/4", "invoice_number": "SAT/1", "mode": "wallet",
                               "is_refund": True, "amount": -5000, "on": ON})
    assert lines(to_wallet) == sorted([("patient_debtors", 5000, 0), ("patient_advances", 0, 5000)])


def test_waivers_and_cancelled_receipts():
    waiver = payment_draft({"receipt_number": "RCP/5", "invoice_number": "SAT/1", "mode": "waiver",
                            "is_refund": False, "amount": 1000, "on": ON})
    assert lines(waiver) == sorted([("waivers", 1000, 0), ("patient_debtors", 0, 1000)])
    assert payment_draft({"receipt_number": "RCP/6", "invoice_number": "SAT/1", "mode": "cash",
                          "is_refund": False, "amount": 1000, "cancelled": True, "on": ON}) is None


def test_advances_by_mode_and_the_movements_posted_elsewhere():
    deposit = wallet_draft({"kind": "deposit", "amount": 200000, "mode": "upi", "receipt_number": "RCP/7", "on": ON})
    assert lines(deposit) == sorted([("bank_upi", 200000, 0), ("patient_advances", 0, 200000)])
    withdrawal = wallet_draft({"kind": "withdrawal", "amount": -20000, "mode": "cash", "on": ON})
    assert lines(withdrawal) == sorted([("patient_advances", 20000, 0), ("cash", 0, 20000)])
    assert wallet_draft({"kind": "applied", "amount": -5000, "on": ON}) is None
    assert wallet_draft({"kind": "refund_credit", "amount": 5000, "on": ON}) is None
    # Cancelling a Rs 50 wallet receipt correctly puts Rs 50 back: nothing to post.
    assert wallet_draft({"kind": "adjustment", "amount": 5000, "payment_linked": True, "linked_amount": 5000,
                         "on": ON}) is None
    # The old defect took Rs 50 again instead: Rs 100 of movement with no counterpart goes to suspense.
    assert lines(wallet_draft({"kind": "adjustment", "amount": -5000, "payment_linked": True,
                               "linked_amount": 5000, "on": ON})) == sorted(
        [("patient_advances", 10000, 0), ("suspense", 0, 10000)])
    assert lines(wallet_draft({"kind": "adjustment", "amount": -300, "on": ON})) == sorted(
        [("patient_advances", 300, 0), ("suspense", 0, 300)])


def test_an_unreceipted_admission_advance_goes_to_suspense():
    draft = legacy_advance_draft({"ip_number": "IP26-00004", "invoice_number": "SAT/9", "amount": 1000000,
                                  "on": ON})
    assert lines(draft) == sorted([("unreceipted_advances", 1000000, 0), ("patient_debtors", 0, 1000000)])
    assert legacy_advance_draft({"ip_number": "x", "invoice_number": "y", "amount": 5, "on": ON,
                                 "invoice_cancelled": True}) is None


def test_booking_a_claim_to_the_bill_moves_it_to_insurance_receivable():
    booked = payment_draft({"receipt_number": "RCP/8", "invoice_number": "SAT/2", "mode": "insurance",
                            "is_refund": False, "amount": 5800000, "on": ON})
    assert booked.voucher_type == "journal"
    assert lines(booked) == sorted([("insurance_receivable", 5800000, 0), ("patient_debtors", 0, 5800000)])


def test_a_payer_settlement_clears_insurance_receivable():
    base = {"claim_number": "CLM/26-27/00001", "payer_name": "Health TPA", "on": ON, "mode": "net_banking"}
    draft = settlement_draft({**base, "received": 5000000, "tds": 500000, "deduction": 300000})
    assert draft.voucher_type == "receipt"
    assert lines(draft) == sorted([("bank_neft", 5000000, 0), ("tds_receivable", 500000, 0),
                                   ("claim_deductions", 300000, 0), ("insurance_receivable", 0, 5800000)])
    write_off = settlement_draft({**base, "received": 0, "tds": 0, "deduction": 300000})
    assert write_off.voucher_type == "journal"
    assert lines(write_off) == sorted([("claim_deductions", 300000, 0), ("insurance_receivable", 0, 300000)])
    assert settlement_draft({**base, "received": 100, "cancelled": True}) is None
    with pytest.raises(PostingError):
        settlement_draft({**base, "mode": "cash", "received": 100})


def test_balance_checks():
    with pytest.raises(PostingError):
        check_balanced([Line("cash", debit=100)])
    with pytest.raises(PostingError):
        check_balanced([Line("cash", debit=100), Line("patient_debtors", credit=90)])
    with pytest.raises(PostingError):
        check_balanced([Line("cash", debit=100, credit=100), Line("patient_debtors", credit=0)])


def test_merge_combines_a_ledger_on_the_same_side():
    merged = merge([Line("income_other", credit=100), Line("income_other", credit=50), Line("cash", debit=150),
                    Line("gst_output", credit=0)])
    assert [(l.ledger, l.debit, l.credit) for l in merged] == [("income_other", 0, 150), ("cash", 150, 0)]


def test_fingerprint_changes_with_amounts_not_line_order():
    a = Draft("sales", ON, "x", [Line("cash", debit=1), Line("income_other", credit=1)])
    b = Draft("sales", ON, "y", [Line("income_other", credit=1), Line("cash", debit=1)])
    c = Draft("sales", ON, "x", [Line("cash", debit=2), Line("income_other", credit=2)])
    assert a.fingerprint() == b.fingerprint() != c.fingerprint()
