"""Invoice arithmetic.

Deliberately free of database and framework: given lines in, totals out. That
makes every rounding decision testable without a running Postgres, which
matters because a rounding error here is money and nobody notices it until the
drawer is short.

The rules, in the order they apply:

1. A line's gross is rate x quantity.
2. A line discount reduces the taxable value, not the tax — you cannot charge
   tax on money the patient did not pay.
3. An invoice-level discount is apportioned across lines in proportion to
   their value, with the remainder assigned to the largest line so the parts
   always sum exactly to the whole.
4. Tax is computed per line, because different lines can carry different
   rates, and only then summed.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from app.billing.money import apply_percentage, compute_tax, round_paise


@dataclass
class LineInput:
    description: str
    unit_rate_paise: int
    quantity: int = 1
    tax_percent: int = 0
    discount_paise: int = 0
    code: Optional[str] = None
    hsn_sac_code: Optional[str] = None
    service_item_id: Optional[str] = None
    #: Carried through untouched; it explains the line, it does not price it.
    remark: Optional[str] = None


@dataclass
class ComputedLine:
    description: str
    remark: Optional[str]
    code: Optional[str]
    hsn_sac_code: Optional[str]
    service_item_id: Optional[str]
    quantity: int
    unit_rate_paise: int
    gross_paise: int
    discount_paise: int
    taxable_paise: int
    tax_percent: int
    tax_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int


@dataclass
class ComputedInvoice:
    lines: List[ComputedLine] = field(default_factory=list)
    gross_paise: int = 0
    discount_paise: int = 0
    taxable_paise: int = 0
    cgst_paise: int = 0
    sgst_paise: int = 0
    igst_paise: int = 0
    total_paise: int = 0

    @property
    def tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise


class BillingError(Exception):
    pass


def _apportion(total_discount: int, weights: List[int]) -> List[int]:
    """Split a discount across lines in proportion to their value.

    The last unit of currency is the interesting part: proportional shares
    rarely divide evenly, so the shares are floored and the remainder is given
    to the largest line. The parts therefore always sum to exactly the whole,
    which a simple round-each-share would not guarantee.
    """
    if total_discount <= 0 or not weights:
        return [0] * len(weights)

    basis = sum(weights)
    if basis <= 0:
        return [0] * len(weights)
    if total_discount > basis:
        raise BillingError("The discount is larger than the amount being billed.")

    shares = [
        int(Decimal(total_discount) * Decimal(weight) / Decimal(basis))
        for weight in weights
    ]
    remainder = total_discount - sum(shares)
    if remainder:
        largest = max(range(len(weights)), key=lambda index: weights[index])
        shares[largest] += remainder
    return shares


def compute_invoice(
    lines: List[LineInput],
    *,
    invoice_discount_paise: int = 0,
    inter_state: bool = False,
) -> ComputedInvoice:
    """Turn priced lines into a complete, internally consistent invoice."""
    if not lines:
        raise BillingError("An invoice needs at least one item.")

    for line in lines:
        if line.quantity <= 0:
            raise BillingError(f"Quantity must be at least 1 for {line.description}.")
        if line.unit_rate_paise < 0:
            raise BillingError(f"A negative rate is not valid for {line.description}.")
        if line.discount_paise < 0:
            raise BillingError(f"A negative discount is not valid for {line.description}.")

    gross_values = [line.unit_rate_paise * line.quantity for line in lines]
    for index, line in enumerate(lines):
        if line.discount_paise > gross_values[index]:
            raise BillingError(
                f"The discount on {line.description} is larger than the item itself."
            )

    after_line_discount = [
        gross - line.discount_paise for gross, line in zip(gross_values, lines)
    ]
    apportioned = _apportion(invoice_discount_paise, after_line_discount)

    computed = ComputedInvoice()
    for index, line in enumerate(lines):
        gross = gross_values[index]
        discount = line.discount_paise + apportioned[index]
        taxable = gross - discount
        breakdown = compute_tax(taxable, Decimal(line.tax_percent), inter_state=inter_state)

        computed.lines.append(
            ComputedLine(
                description=line.description,
                remark=line.remark,
                code=line.code,
                hsn_sac_code=line.hsn_sac_code,
                service_item_id=line.service_item_id,
                quantity=line.quantity,
                unit_rate_paise=line.unit_rate_paise,
                gross_paise=gross,
                discount_paise=discount,
                taxable_paise=taxable,
                tax_percent=line.tax_percent,
                tax_paise=breakdown.total_tax_paise,
                cgst_paise=breakdown.cgst_paise,
                sgst_paise=breakdown.sgst_paise,
                igst_paise=breakdown.igst_paise,
                total_paise=breakdown.total_paise,
            )
        )

        computed.gross_paise += gross
        computed.discount_paise += discount
        computed.taxable_paise += taxable
        computed.cgst_paise += breakdown.cgst_paise
        computed.sgst_paise += breakdown.sgst_paise
        computed.igst_paise += breakdown.igst_paise
        computed.total_paise += breakdown.total_paise

    return computed


def validate_payment(
    *, amount_paise: int, balance_paise: int, allow_overpayment: bool = False
) -> None:
    """Reject a payment that cannot be right before it reaches the ledger."""
    if amount_paise == 0:
        raise BillingError("A payment must be for more than zero.")
    if amount_paise < 0:
        raise BillingError("Use the refund flow rather than a negative payment.")
    if not allow_overpayment and amount_paise > balance_paise:
        raise BillingError(
            "That is more than the outstanding balance. Correct the amount, "
            "or record the excess as a separate advance."
        )
