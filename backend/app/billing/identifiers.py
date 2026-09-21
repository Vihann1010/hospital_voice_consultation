"""Identifiers: UHID, invoice numbers, receipt numbers.

Two different problems, deliberately solved differently.

**UHID** is the patient's permanent hospital number. It is spoken aloud at a
counter, written on a paper file and read back over a phone, so it is built to
survive that: no characters that are confused when handwritten or dictated.

**Invoice and receipt numbers** are financial documents. Indian GST rules
require them to be sequential within a financial year and gapless — an auditor
who finds SAT/26-27/000041 and SAT/26-27/000043 with nothing between them will
ask what happened to 42, and "the transaction rolled back" is not a comfortable
answer. They are therefore allocated from a database counter row under a lock,
not from a max()+1 query, which two concurrent cashiers would race.
"""
import re
from datetime import date
from typing import Optional

from app.core.config import settings
from app.core.financial_year import label_for
from app.core.clock import local_today

# Excluded from UHIDs on purpose:
#   I, 1, J  — indistinguishable when handwritten
#   O, 0, Q  — likewise
#   S, 5      — likewise, and often confused when dictated
#   B, 8      — confused when dictated over a phone
#   Z, 2      — confused when handwritten
# Each ambiguous pair is resolved by keeping exactly one member, so a
# misheard or mistyped character has a single unambiguous correction.
UHID_ALPHABET = "ACDEFGHKLMNPRTUVWXY34679"

# The site's three letters, at the front of every UHID and invoice number. It
# was "SAT", written here, so a second site printed another hospital's name on
# its patients' cards and its bills. Three letters exactly: the UHID is sized
# to be read over a counter, and existing numbers are matched by this pattern.
PREFIX = settings.DOCUMENT_PREFIX

UHID_PATTERN = re.compile(rf"^{PREFIX}(\d{{2}})([A-Z0-9]{{6}})$")


def financial_year(on: Optional[date] = None) -> str:
    """The Indian financial year label for a date: April to March.

    A bill raised on 31 March and one raised on 1 April belong to different
    years, and the numbering restarts. Getting this wrong misfiles a whole
    day's revenue — so the rule lives in one module and this defers to it
    rather than restating it.
    """
    return label_for(on)


def build_uhid(sequence: int, on: Optional[date] = None) -> str:
    """A patient's permanent number, e.g. SAT26A4K7QM for the prefix SAT.

    The year prefix makes the registration era obvious at a glance; the
    encoded suffix keeps it short enough to say over a counter.
    """
    today = on or local_today()
    year = today.year % 100

    base = len(UHID_ALPHABET)
    value = sequence
    encoded = ""
    while value > 0:
        value, remainder = divmod(value, base)
        encoded = UHID_ALPHABET[remainder] + encoded
    encoded = encoded.rjust(6, UHID_ALPHABET[0])

    if len(encoded) > 6:
        # Beyond ~594 million patients per year. Fail rather than silently
        # truncate into a collision.
        raise ValueError("UHID sequence has exceeded the encodable range.")
    return f"{PREFIX}{year:02d}{encoded}"


def is_valid_uhid(value: str) -> bool:
    if not value:
        return False
    match = UHID_PATTERN.match(value.strip().upper())
    if match is None:
        return False
    return all(character in UHID_ALPHABET for character in match.group(2))


def normalise_uhid(value: str) -> str:
    """Tidy a UHID typed or dictated at the counter.

    Staff will type O for zero and I for one out of habit, and the ambiguous
    characters were excluded precisely so those inputs are unambiguous to
    correct rather than being rejected as not-found.
    """
    cleaned = (value or "").strip().upper().replace(" ", "").replace("-", "")
    # Each maps an excluded character onto the one member of its pair that
    # the alphabet actually uses.
    substitutions = {
        "O": "D", "0": "D",     # zero and O are written for D surprisingly often
        "I": "L", "1": "L", "J": "L",
        "Q": "D",
        "S": "5", "5": "X",
        "B": "8", "8": "H",
        "Z": "2", "2": "7",
    }
    if cleaned.startswith(PREFIX) and len(cleaned) == 11:
        prefix, suffix = cleaned[:5], cleaned[5:]
        suffix = "".join(substitutions.get(c, c) if c not in UHID_ALPHABET else c
                         for c in suffix)
        return prefix + suffix
    return cleaned


def build_invoice_number(sequence: int, on: Optional[date] = None) -> str:
    """SAT/26-27/000041 — sequential within the financial year."""
    return f"{PREFIX}/{financial_year(on)}/{sequence:06d}"


def build_receipt_number(sequence: int, on: Optional[date] = None) -> str:
    """RCP/26-27/000041 — receipts are numbered separately from invoices."""
    return f"RCP/{financial_year(on)}/{sequence:06d}"
