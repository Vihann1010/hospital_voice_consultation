"""Money arithmetic.

Every monetary amount in this system is an integer number of **paise**, never
a float and never a Decimal in the database. Floats cannot represent 0.10
exactly, so a day of ₹0.005 errors compounds into a cash drawer that does not
reconcile, and nobody can tell you why. Integers make the arithmetic exact and
the storage unambiguous.

Rounding happens in exactly one place — `round_paise` — and always half-up,
which is what Indian invoicing expects and what a cashier counting notes
expects. Banker's rounding (Python's default) would surprise both.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

PAISE_PER_RUPEE = 100


def rupees_to_paise(amount: str | int | float | Decimal) -> int:
    """Convert a human-entered rupee amount to paise.

    Accepts float for convenience at the edges (a JSON body, a spreadsheet
    import) but converts through Decimal immediately, so the float never
    participates in arithmetic.
    """
    value = Decimal(str(amount))
    return int((value * PAISE_PER_RUPEE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees(paise: int) -> Decimal:
    """Exact rupee value, for display and printing."""
    return (Decimal(paise) / PAISE_PER_RUPEE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def format_inr(paise: int) -> str:
    """Indian-format currency: ₹1,23,456.78 — lakhs, not thousands.

    Written out rather than delegated to `locale`, because the correct locale
    is rarely installed in a container and a silently wrong grouping on a
    printed bill is the kind of thing nobody notices until an auditor does.
    """
    negative = paise < 0
    whole, fraction = divmod(abs(paise), PAISE_PER_RUPEE)
    digits = str(whole)

    if len(digits) <= 3:
        grouped = digits
    else:
        last_three = digits[-3:]
        rest = digits[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts + [last_three])

    return f"{'-' if negative else ''}₹{grouped}.{fraction:02d}"


def round_paise(value: Decimal) -> int:
    """The single rounding point in the system. Half-up, to whole paise."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def apply_percentage(amount_paise: int, percent: Decimal) -> int:
    """A percentage of an amount, rounded once at the end."""
    return round_paise(Decimal(amount_paise) * Decimal(percent) / Decimal(100))


def total(amounts: Iterable[int]) -> int:
    return sum(amounts)


# ---------------------------------------------------------------------------
# GST
# ---------------------------------------------------------------------------
# Most healthcare services provided by a clinical establishment are exempt
# under Notification 12/2017 Central Tax (Rate), so the default rate is zero.
# The machinery exists because non-clinical items a hospital does sell —
# retail pharmacy, some cosmetic procedures, room categories — are not exempt,
# and because an invoice that cannot express tax cannot be corrected later
# without a schema change.
#
# Intra-state supply splits equally into CGST and SGST; inter-state is a
# single IGST at the full rate. A hospital serving walk-in patients is almost
# always intra-state, which is the default here.


@dataclass(frozen=True)
class TaxBreakdown:
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int

    @property
    def total_tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise

    @property
    def total_paise(self) -> int:
        return self.taxable_paise + self.total_tax_paise


def compute_tax(
    taxable_paise: int, rate_percent: Decimal, *, inter_state: bool = False
) -> TaxBreakdown:
    """Split tax into CGST/SGST or IGST.

    The halves are computed so they always sum exactly to the total tax: the
    second half is the remainder rather than a second rounding, which stops
    a one-paisa discrepancy appearing between the tax lines and the total.
    """
    rate = Decimal(rate_percent)
    if rate <= 0:
        return TaxBreakdown(taxable_paise, 0, 0, 0)

    tax = apply_percentage(taxable_paise, rate)
    if inter_state:
        return TaxBreakdown(taxable_paise, 0, 0, tax)

    cgst = tax // 2
    sgst = tax - cgst
    return TaxBreakdown(taxable_paise, cgst, sgst, 0)
