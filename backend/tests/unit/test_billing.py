"""Money arithmetic, invoice totals and identifiers.

Billing errors are silent: nobody notices a paisa, and by the time a drawer is
short at closing time the cause is a week old. These tests exist so the
arithmetic is proved rather than assumed.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.billing.engine import (
    BillingError,
    LineInput,
    compute_invoice,
    validate_payment,
)
from app.billing.identifiers import (
    UHID_ALPHABET,
    build_invoice_number,
    build_uhid,
    financial_year,
    is_valid_uhid,
    normalise_uhid,
)
from app.billing.money import (
    apply_percentage,
    compute_tax,
    format_inr,
    paise_to_rupees,
    rupees_to_paise,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------- money
@pytest.mark.parametrize(
    "amount,expected",
    [("500", 50000), ("500.50", 50050), ("0.01", 1), ("1234.56", 123456),
     (0.1, 10), ("0.005", 1), ("0.004", 0)],
)
def test_rupees_convert_exactly(amount, expected):
    assert rupees_to_paise(amount) == expected


def test_integer_paise_avoids_float_drift():
    """0.1 + 0.2 != 0.3 in binary floating point. In paise it does."""
    assert rupees_to_paise("0.1") + rupees_to_paise("0.2") == 30
    assert paise_to_rupees(30) == Decimal("0.30")


@pytest.mark.parametrize(
    "paise,expected",
    [(50000, "₹500.00"), (123456, "₹1,234.56"), (10000000, "₹1,00,000.00"),
     (12345678, "₹1,23,456.78"), (100, "₹1.00"), (-50000, "-₹500.00"), (0, "₹0.00")],
)
def test_currency_uses_indian_grouping(paise, expected):
    """Lakhs, not thousands. A wrong grouping on a printed bill is noticed by
    an auditor long before it is noticed by anyone else."""
    assert format_inr(paise) == expected


@pytest.mark.parametrize("taxable", [50000, 33333, 1, 99999, 12345, 7])
def test_gst_halves_always_sum_to_the_tax(taxable):
    """CGST + SGST must equal the total exactly — no orphan paisa."""
    breakdown = compute_tax(taxable, Decimal(18))
    assert breakdown.cgst_paise + breakdown.sgst_paise == apply_percentage(
        taxable, Decimal(18)
    )


def test_healthcare_is_exempt_by_default():
    breakdown = compute_tax(50000, Decimal(0))
    assert breakdown.total_tax_paise == 0
    assert breakdown.total_paise == 50000


def test_inter_state_supply_uses_igst_only():
    breakdown = compute_tax(50000, Decimal(18), inter_state=True)
    assert breakdown.igst_paise == 9000
    assert breakdown.cgst_paise == breakdown.sgst_paise == 0


# ------------------------------------------------------------------ invoices
def test_a_typical_opd_bill():
    invoice = compute_invoice([
        LineInput("Registration", 10000),
        LineInput("OPD consultation", 50000),
    ])
    assert invoice.total_paise == 60000


@pytest.mark.parametrize("discount", [1, 7, 9999, 10000])
def test_apportioned_discount_sums_exactly(discount):
    """The discount split across lines must equal the discount given.

    Rounding each share independently would lose or gain a paisa; the last
    share is the remainder instead.
    """
    invoice = compute_invoice(
        [LineInput("A", 33333), LineInput("B", 33333), LineInput("C", 33334)],
        invoice_discount_paise=discount,
    )
    assert sum(line.discount_paise for line in invoice.lines) == discount


def test_tax_follows_the_discounted_value():
    """Tax is charged on what the patient pays, not on the list price."""
    invoice = compute_invoice(
        [LineInput("Retail item", 100000, tax_percent=18, discount_paise=20000)]
    )
    line = invoice.lines[0]
    assert line.taxable_paise == 80000
    assert line.tax_paise == 14400


def test_a_line_keeps_its_own_remark():
    """The clerk's note travels with the line it explains, untouched."""
    invoice = compute_invoice(
        [
            LineInput("Dressing", 20000, remark="Second sitting"),
            LineInput("Consultation", 50000),
        ]
    )
    assert [line.remark for line in invoice.lines] == ["Second sitting", None]


def test_a_line_discount_and_a_bill_discount_both_apply():
    """A discount on one charge comes off before the bill-wide discount.

    The line keeps its own 200, then takes its share of the 100 given on the
    whole bill, and the parts still sum to what was allowed.
    """
    invoice = compute_invoice(
        [
            LineInput("Dressing", 50000, discount_paise=20000),
            LineInput("Consultation", 30000),
        ],
        invoice_discount_paise=10000,
    )
    assert invoice.gross_paise == 80000
    assert invoice.discount_paise == 30000
    assert invoice.taxable_paise == 50000
    assert invoice.total_paise == 50000
    assert sum(line.discount_paise for line in invoice.lines) == 30000


def test_a_rate_set_at_the_counter_is_what_is_charged():
    """Reception is sometimes told to charge something other than the list."""
    invoice = compute_invoice([LineInput("X-ray knee", 35000, quantity=2)])
    assert invoice.gross_paise == 70000
    assert invoice.total_paise == 70000


def test_mixed_tax_rates_on_one_bill():
    invoice = compute_invoice([
        LineInput("Consultation (exempt)", 50000, tax_percent=0),
        LineInput("Crepe bandage", 12000, tax_percent=12),
    ])
    assert invoice.total_paise == 50000 + 12000 + 1440


@pytest.mark.parametrize(
    "lines,discount",
    [
        ([LineInput("X", 1000)], 5000),                       # discount > bill
        ([], 0),                                              # nothing billed
        ([LineInput("X", 1000, quantity=0)], 0),              # zero quantity
        ([LineInput("X", 1000, discount_paise=2000)], 0),     # line discount > line
    ],
)
def test_impossible_invoices_are_rejected(lines, discount):
    with pytest.raises(BillingError):
        compute_invoice(lines, invoice_discount_paise=discount)


@pytest.mark.parametrize(
    "amount,balance",
    [(70000, 60000), (0, 60000), (-100, 60000)],
)
def test_impossible_payments_are_rejected(amount, balance):
    with pytest.raises(BillingError):
        validate_payment(amount_paise=amount, balance_paise=balance)


def test_a_valid_payment_is_accepted():
    validate_payment(amount_paise=50000, balance_paise=60000)


# --------------------------------------------------------------- identifiers
@pytest.mark.parametrize(
    "day,expected",
    [(date(2026, 3, 31), "25-26"), (date(2026, 4, 1), "26-27"),
     (date(2026, 12, 31), "26-27"), (date(2027, 3, 31), "26-27")],
)
def test_financial_year_turns_over_in_april(day, expected):
    """A bill on 31 March and one on 1 April belong to different years."""
    assert financial_year(day) == expected


def test_uhids_are_unique_and_valid():
    day = date(2026, 8, 10)
    generated = {build_uhid(sequence, day) for sequence in range(1, 5000)}
    assert len(generated) == 4999
    assert all(is_valid_uhid(value) for value in generated)


def test_uhids_avoid_characters_confused_when_spoken_or_written():
    """A UHID is dictated over a counter and written on a paper file."""
    day = date(2026, 8, 10)
    sample = "".join(build_uhid(sequence, day)[5:] for sequence in range(1, 3000))
    assert not set("IO01SBQJZ258") & set(sample)
    assert not set(sample) - set(UHID_ALPHABET)


def test_mistyped_uhids_are_corrected():
    """Staff type O for zero and I for one out of habit."""
    day = date(2026, 8, 10)
    real = build_uhid(42, day)
    assert normalise_uhid(real.replace("D", "O").replace("L", "I")) == real
    assert normalise_uhid(f"  {real.lower()}  ") == real


def test_invoice_numbers_are_sequential_within_the_year():
    day = date(2026, 8, 10)
    assert build_invoice_number(41, day) == "SAT/26-27/000041"
    assert build_invoice_number(1, day) < build_invoice_number(2, day)
