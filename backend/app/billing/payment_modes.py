"""What each payment mode has to record about itself.

A receipt that says only "₹500, card" cannot be reconciled against anything.
When the bank statement and the day's takings disagree — which they will —
the questions asked are *which* card, *whose* cheque, *what* UPI reference,
and a system that never captured them cannot answer.

So each mode declares the fields it needs, and the counter is held to them:

  cash          nothing; the cash book is the record
  card          last four digits, and the approval code if the machine gave one
  upi           the transaction reference
  net_banking   the transfer reference
  cheque        number, bank and date — a cheque is a promise, not a payment,
                and it is traced by these three until it clears
  insurance     the payer and their claim reference
  waiver        who authorised writing the money off, and why
  wallet        nothing; the money was already receipted when it was deposited

Two deliberate refusals. A field that is required is required — an empty
string will not do, because "" in a reference column is indistinguishable
from a clerk who did not look. And unknown fields are rejected rather than
stored, since a typo like "chq_no" would otherwise be saved silently and
never appear on any report.
"""
from typing import Any, Dict, List, Mapping, Optional

from app.models.enums import PaymentMode


class PaymentModeError(ValueError):
    pass


class Field:
    __slots__ = ("name", "label", "required", "max_length", "digits")

    def __init__(
        self,
        name: str,
        label: str,
        *,
        required: bool = True,
        max_length: int = 64,
        digits: Optional[int] = None,
    ) -> None:
        self.name = name
        self.label = label
        self.required = required
        self.max_length = max_length
        # Exactly this many digits, nothing else. Used for a card's last four,
        # where "1234 " or "**34" is a mistake worth catching at the counter.
        self.digits = digits


MODE_FIELDS: Dict[PaymentMode, List[Field]] = {
    PaymentMode.CASH: [],
    PaymentMode.CARD: [
        Field("last4", "Last 4 digits", digits=4),
        Field("approval_code", "Approval code", required=False, max_length=32),
        Field("card_network", "Card network", required=False, max_length=32),
    ],
    PaymentMode.UPI: [Field("reference", "UPI reference", max_length=64)],
    PaymentMode.NET_BANKING: [
        Field("reference", "Transfer reference", max_length=64),
        Field("bank_name", "Bank", required=False, max_length=120),
    ],
    PaymentMode.CHEQUE: [
        Field("cheque_number", "Cheque number", max_length=32),
        Field("bank_name", "Bank", max_length=120),
        Field("cheque_date", "Cheque date", max_length=10),
    ],
    PaymentMode.INSURANCE: [
        Field("payer_name", "Insurer or TPA", max_length=120),
        Field("claim_reference", "Claim reference", required=False, max_length=64),
    ],
    PaymentMode.WAIVER: [
        Field("approved_by", "Approved by", max_length=120),
        Field("reason", "Reason", max_length=255),
    ],
    PaymentMode.WALLET: [],
}

# Modes that move money into the till today. A wallet payment does not: the
# cash arrived when the patient deposited it, and counting it again here is
# the double-count that makes a day's takings irreconcilable. A waiver never
# arrives at all.
COLLECTING_MODES = frozenset(
    {
        PaymentMode.CASH,
        PaymentMode.CARD,
        PaymentMode.UPI,
        PaymentMode.NET_BANKING,
        PaymentMode.CHEQUE,
        PaymentMode.INSURANCE,
    }
)


def validate_mode_details(
    mode: PaymentMode, details: Optional[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Check and normalise what was recorded about the instrument."""
    spec = MODE_FIELDS.get(mode, [])
    given = dict(details or {})

    known = {field.name for field in spec}
    unknown = sorted(set(given) - known)
    if unknown:
        raise PaymentModeError(
            f"{', '.join(unknown)} is not recorded for a {mode.value} payment."
            if len(unknown) == 1
            else f"{', '.join(unknown)} are not recorded for a {mode.value} payment."
        )

    cleaned: Dict[str, Any] = {}
    for field in spec:
        raw = given.get(field.name)
        value = str(raw).strip() if raw is not None else ""
        if not value:
            if field.required:
                raise PaymentModeError(f"{field.label} is needed for a {mode.value} payment.")
            continue
        if len(value) > field.max_length:
            raise PaymentModeError(f"{field.label} is too long.")
        if field.digits is not None and not (
            value.isdigit() and len(value) == field.digits
        ):
            raise PaymentModeError(f"{field.label} must be {field.digits} digits.")
        cleaned[field.name] = value
    return cleaned


def summarise(mode: PaymentMode, details: Optional[Mapping[str, Any]]) -> str:
    """One line for the receipt, e.g. "Cheque 004512, HDFC Bank, 12-09-2026"."""
    values = dict(details or {})
    if mode is PaymentMode.CARD and values.get("last4"):
        return f"Card ending {values['last4']}"
    if mode is PaymentMode.CHEQUE:
        parts = [values.get("cheque_number"), values.get("bank_name"), values.get("cheque_date")]
        return "Cheque " + ", ".join(part for part in parts if part)
    if mode in (PaymentMode.UPI, PaymentMode.NET_BANKING) and values.get("reference"):
        label = "UPI" if mode is PaymentMode.UPI else "Bank transfer"
        return f"{label} {values['reference']}"
    if mode is PaymentMode.INSURANCE and values.get("payer_name"):
        return f"Insurance — {values['payer_name']}"
    if mode is PaymentMode.WAIVER and values.get("approved_by"):
        return f"Waived, approved by {values['approved_by']}"
    if mode is PaymentMode.WALLET:
        return "From patient wallet"
    return mode.value.replace("_", " ").title()


def describe() -> List[Dict[str, Any]]:
    """The whole table, for the counter screen to render its own fields."""
    return [
        {
            "mode": mode.value,
            "collects_cash": mode in COLLECTING_MODES,
            "fields": [
                {
                    "name": field.name,
                    "label": field.label,
                    "required": field.required,
                    "digits": field.digits,
                }
                for field in fields
            ],
        }
        for mode, fields in MODE_FIELDS.items()
    ]
