"""Posting rules: what each counter record means in the books.

Pure functions from plain values to voucher drafts, so every rule is tested
without a database. The books are derived from the bills, receipts and wallet
entries — never typed twice — and a draft that does not add up is refused
with a reason rather than posted with a plug.

* A bill (sales): Dr patients receivable for the total, Dr discounts allowed,
  Cr income for the gross by what was billed, Cr GST output.
* A receipt: Dr cash or the bank clearing ledger for its mode, Cr patients
  receivable. A refund is the same the other way round.
* A bill settled from the wallet: Dr patient advances, Cr patients receivable.
  The wallet entry for it is not posted separately, or it would count twice.
* A waiver: Dr waivers and write-offs. An insurance receipt: Dr insurance
  receivable.
* An advance deposit: Dr cash or bank, Cr patient advances. Paying it back is
  the reverse.
* An advance typed on an admission before advances were receipted and applied
  to the final bill: Dr "advances not receipted", Cr patients receivable — a
  suspense ledger the accountant clears, rather than invented cash.
* A TPA or insurer settling a claim: Dr the bank ledger for what arrived, Dr
  TDS deducted by payers, Dr insurance claim deductions for what they refused,
  Cr insurance receivable for the three together. The payer's share reached
  insurance receivable earlier, when it was booked to the bill as an
  insurance payment.
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

INCOME_BY_CATEGORY = {
    "consultation": "income_consultation",
    "registration": "income_registration",
    "procedure": "income_procedure",
    "investigation": "income_investigation",
    "other": "income_other",
}
INCOME_BY_SOURCE = {"IPD": "income_ipd", "Lab": "income_lab"}

MODE_LEDGER = {
    "cash": "cash",
    "card": "bank_card",
    "upi": "bank_upi",
    "net_banking": "bank_neft",
    "cheque": "cheques",
    "insurance": "insurance_receivable",
    "waiver": "waivers",
    "wallet": "patient_advances",
}
TILL_MODES = {"cash", "card", "upi", "net_banking", "cheque"}


class PostingError(ValueError):
    """A record that cannot be posted as it stands."""


@dataclass
class Line:
    ledger: str            # a system key, or "ledger:<uuid>"
    debit: int = 0
    credit: int = 0
    narration: Optional[str] = None


@dataclass
class Draft:
    voucher_type: str
    on: date
    narration: str
    lines: List[Line]
    patient_id: Any = None
    consultant_id: Any = None

    def fingerprint(self) -> str:
        """What the voucher says, for noticing when its source has changed."""
        body = [self.voucher_type, self.on.isoformat(),
                sorted((line.ledger, line.debit, line.credit) for line in self.lines)]
        return hashlib.sha256(json.dumps(body).encode()).hexdigest()


def check_balanced(lines: Iterable[Line]) -> None:
    lines = list(lines)
    if len(lines) < 2:
        raise PostingError("A voucher needs at least two lines.")
    for line in lines:
        if line.debit < 0 or line.credit < 0:
            raise PostingError("An amount cannot be negative.")
        if (line.debit == 0) == (line.credit == 0):
            raise PostingError("Each line is either a debit or a credit, and not zero.")
    debits = sum(line.debit for line in lines)
    credits = sum(line.credit for line in lines)
    if debits != credits:
        raise PostingError(f"Debits {debits / 100:,.2f} and credits {credits / 100:,.2f} do not agree.")


def merge(lines: Iterable[Line]) -> List[Line]:
    """One line per ledger and side, zero lines dropped, in first-seen order."""
    order: List[tuple] = []
    totals: Dict[tuple, int] = {}
    for line in lines:
        for side, amount in (("dr", line.debit), ("cr", line.credit)):
            if amount:
                key = (line.ledger, side)
                if key not in totals:
                    order.append(key)
                    totals[key] = 0
                totals[key] += amount
    return [Line(ledger, debit=totals[(ledger, side)] if side == "dr" else 0,
                 credit=totals[(ledger, side)] if side == "cr" else 0) for ledger, side in order]


def income_ledger(source: Optional[str], category: Optional[str]) -> str:
    if source in INCOME_BY_SOURCE:
        return INCOME_BY_SOURCE[source]
    return INCOME_BY_CATEGORY.get(category or "other", "income_other")


def invoice_draft(invoice: Dict[str, Any]) -> Optional[Draft]:
    """A bill. None when there is nothing for the books: a draft or cancelled bill."""
    if invoice["status"] == "cancelled" or invoice.get("issued_on") is None:
        return None
    gross, discount, tax, total = (int(invoice[key]) for key in ("gross", "discount", "tax", "total"))
    if gross == 0 and total == 0:
        return None
    if gross - discount + tax != total:
        raise PostingError(f"Bill {invoice['number']}: gross less discount plus tax is not the total.")
    lines_gross = sum(int(line["gross"]) for line in invoice["lines"])
    if lines_gross != gross:
        raise PostingError(f"Bill {invoice['number']}: its lines do not add up to its gross.")
    lines = [Line("patient_debtors", debit=total), Line("discount_allowed", debit=discount)]
    lines += [Line(income_ledger(invoice.get("source"), line.get("category")), credit=int(line["gross"]))
              for line in invoice["lines"]]
    lines.append(Line("gst_output", credit=tax))
    lines = merge(lines)
    check_balanced(lines)
    return Draft("sales", invoice["issued_on"], f"Bill {invoice['number']} - {invoice.get('patient_name', '')}".strip(),
                 lines, patient_id=invoice.get("patient_id"), consultant_id=invoice.get("consultant_id"))


def payment_draft(payment: Dict[str, Any]) -> Optional[Draft]:
    """A receipt or refund against a bill."""
    if payment.get("cancelled") or not payment["amount"]:
        return None
    mode = payment["mode"]
    if mode not in MODE_LEDGER:
        raise PostingError(f"Receipt {payment['receipt_number']}: no ledger for payment mode {mode}.")
    amount = abs(int(payment["amount"]))
    ledger = MODE_LEDGER[mode]
    till = mode in TILL_MODES
    if payment.get("is_refund"):
        lines = [Line("patient_debtors", debit=amount), Line(ledger, credit=amount)]
        kind, word = ("payment" if till else "journal"), "Refund"
    else:
        lines = [Line(ledger, debit=amount), Line("patient_debtors", credit=amount)]
        kind, word = ("receipt" if till else "journal"), ("Settled from advance" if mode == "wallet" else "Receipt")
    check_balanced(lines)
    return Draft(kind, payment["on"],
                 f"{word} {payment['receipt_number']} on bill {payment['invoice_number']} - "
                 f"{payment.get('patient_name', '')}".strip(" -"),
                 lines, patient_id=payment.get("patient_id"))


def wallet_draft(entry: Dict[str, Any]) -> Optional[Draft]:
    """An advance taken or returned. Movements that belong to a bill are posted with that bill's receipt."""
    kind = entry["kind"]
    amount = int(entry["amount"])
    if amount == 0 or kind in ("applied", "refund_credit"):
        return None
    if kind == "adjustment":
        # An adjustment made by cancelling a wallet receipt should put back
        # exactly what that receipt took (its own signed amount). The receipt's
        # cancellation already reverses its voucher, so a correct adjustment
        # posts nothing; any difference between the two is a wallet movement
        # with no counterpart, and goes to suspense where the accountant sees it.
        expected = int(entry.get("linked_amount") or 0) if entry.get("payment_linked") else 0
        difference = amount - expected
        if difference == 0:
            return None
        lines = ([Line("suspense", debit=difference), Line("patient_advances", credit=difference)] if difference > 0
                 else [Line("patient_advances", debit=-difference), Line("suspense", credit=-difference)])
        check_balanced(lines)
        what = ("Advance adjustment does not match the cancelled receipt it reverses"
                if entry.get("payment_linked") else "Advance adjusted")
        return Draft("journal", entry["on"], f"{what} - {entry.get('patient_name', '')}".strip(" -"),
                     lines, patient_id=entry.get("patient_id"))
    mode = entry.get("mode") or "cash"
    if mode not in TILL_MODES:
        raise PostingError(f"Advance {entry.get('receipt_number')}: {mode} is not money received.")
    ledger = MODE_LEDGER[mode]
    if kind == "deposit":
        lines = [Line(ledger, debit=amount), Line("patient_advances", credit=amount)]
        voucher_type, word = "receipt", "Advance received"
    elif kind == "withdrawal":
        lines = [Line("patient_advances", debit=-amount), Line(ledger, credit=-amount)]
        voucher_type, word = "payment", "Advance returned"
    else:
        raise PostingError(f"Unknown wallet movement {kind}.")
    check_balanced(lines)
    return Draft(voucher_type, entry["on"],
                 f"{word} {entry.get('receipt_number') or ''} - {entry.get('patient_name', '')}".replace("  ", " ").strip(" -"),
                 lines, patient_id=entry.get("patient_id"))


def legacy_advance_draft(record: Dict[str, Any]) -> Optional[Draft]:
    """An unreceipted admission advance that settled part of a final bill."""
    if record.get("invoice_cancelled") or record["amount"] <= 0:
        return None
    lines = [Line("unreceipted_advances", debit=record["amount"]), Line("patient_debtors", credit=record["amount"])]
    return Draft("journal", record["on"],
                 f"Advance recorded on admission {record['ip_number']} before receipts, set against bill "
                 f"{record['invoice_number']}", lines, patient_id=record.get("patient_id"))


SETTLEMENT_MODES = ("net_banking", "cheque", "upi")


def settlement_draft(settlement: Dict[str, Any]) -> Optional[Draft]:
    """Money, TDS and disallowances from a payer against a claim booked to a bill."""
    if settlement.get("cancelled"):
        return None
    received, tds, deduction = (int(settlement.get(key) or 0) for key in ("received", "tds", "deduction"))
    total = received + tds + deduction
    if total == 0:
        return None
    if min(received, tds, deduction) < 0:
        raise PostingError(f"Claim {settlement['claim_number']}: a settlement amount is negative.")
    mode = settlement["mode"]
    if mode not in SETTLEMENT_MODES:
        raise PostingError(f"Claim {settlement['claim_number']}: no ledger for a payer paying by {mode}.")
    lines = merge([
        Line(MODE_LEDGER[mode], debit=received),
        Line("tds_receivable", debit=tds),
        Line("claim_deductions", debit=deduction),
        Line("insurance_receivable", credit=total),
    ])
    check_balanced(lines)
    return Draft("receipt" if received else "journal", settlement["on"],
                 f"Claim {settlement['claim_number']} settled by {settlement.get('payer_name') or 'payer'} - "
                 f"{settlement.get('patient_name', '')}".strip(" -"),
                 lines, patient_id=settlement.get("patient_id"))


def reversed_lines(lines: Iterable[Line]) -> List[Line]:
    return [Line(line.ledger, debit=line.credit, credit=line.debit, narration=line.narration) for line in lines]
