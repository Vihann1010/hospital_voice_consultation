"""Decide what kind of document a page of extracted text actually is.

Whoever uploads a file says what it is, and that declaration is worth having:
a patient photographing their own prescription knows it is a prescription. But
a declaration is not evidence. A patient in a queue taps the nearest tile, a
nurse picks the last one she used, and the wrong parser on a medical document
does not fail loudly — it produces confident nonsense.

So the text is classified independently and the two are compared. Agreement
buys the full analysis. Disagreement buys nothing: the report is marked
unclear and the doctor is told to read the original. That is the whole point
of this module — not to be clever about guessing the kind, but to be able to
say "I am not sure" in a way the rest of the pipeline must respect.

Nothing here uses a language model. These are counted keywords and matched
analyte names, so the same page always classifies the same way and the reason
can be shown on screen.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.investigations.reference_ranges import resolve_analyte
from app.models.enums import DocumentKind

# --- prescription --------------------------------------------------------
# Indian dose notation. "1-0-1" is one tablet in the morning and one at night;
# "1-0-0-0" spells out four slots instead of three. To a range parser both are
# reference intervals, which is exactly how a 40 mg pantoprazole came to be
# reported as a value outside the range 1.0 to 0.0.
_SLOT = r"[0-2](?:\.5)?"
DOSE_PATTERN = re.compile(
    rf"\b{_SLOT}\s*[-–]\s*{_SLOT}\s*[-–]\s*{_SLOT}(?:\s*[-–]\s*{_SLOT})?\b"
)

_RX_MARK = re.compile(r"(?:^|\s)(?:R[xX]|℞)(?:\s|$|[.:])")
_FREQUENCY = re.compile(
    r"\b(?:OD|BD|BID|TDS|TID|QID|QDS|HS|SOS|STAT|PRN|OW|q\d+h)\b", re.IGNORECASE
)
_DOSE_FORM = re.compile(
    r"\b(?:tab|tabs|tablet|cap|caps|capsule|syp|syrup|susp|inj|injection|"
    r"ointment|cream|gel|drops?|sachet|lotion|spray|inhaler)\b\.?",
    re.IGNORECASE,
)
_DIRECTIONS = re.compile(
    r"\b(?:after\s+food|before\s+food|after\s+meals?|before\s+meals?|"
    r"empty\s+stomach|bedtime|with\s+water|for\s+\d+\s*(?:day|days|week|weeks|month|months))\b",
    re.IGNORECASE,
)
_PRESCRIPTION_HEADINGS = re.compile(
    r"\b(?:advice|follow\s*up|review\s+after|c/o|k/c/o|complaints?|"
    r"provisional\s+diagnosis|treatment|medication|prescription)\b",
    re.IGNORECASE,
)

# --- laboratory ----------------------------------------------------------
_LAB_VOCABULARY = re.compile(
    r"\b(?:reference\s+(?:range|interval|value)|biological\s+ref|normal\s+range|"
    r"specimen|sample\s+(?:collected|received|type)|lab(?:oratory)?\s*(?:no|id)|"
    r"pathologist|haematology|hematology|biochemistry|serology|microbiology|"
    r"units?\b\s*$|method|result\s*\(s\)?)\b",
    re.IGNORECASE | re.MULTILINE,
)
# A range printed on its own line beside a value, which is what a lab report
# looks like and a prescription does not.
_PRINTED_RANGE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\b"
)

# --- imaging -------------------------------------------------------------
_MODALITY = re.compile(
    r"\b(?:x[\s-]?ray|xray|radiograph|plain\s+film|mri|magnetic\s+resonance|"
    r"ct\s*scan|computed\s+tomography|usg|ultraso(?:und|nography)|sonograph[yi]|"
    r"doppler|mammogra(?:m|phy)|echocardiogra(?:m|phy)|dexa|pet\s*ct|"
    r"barium|ivp|hsg)\b",
    re.IGNORECASE,
)
_IMAGING_VOCABULARY = re.compile(
    r"\b(?:impression|findings|technique|contrast|radiologist|"
    r"no\s+evidence\s+of|unremarkable|visuali[sz]ed|study\s+reveals|"
    r"axial|sagittal|coronal|anteroposterior|lateral\s+view)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Classification:
    """What the text looks like, and how strongly."""

    kind: Optional[DocumentKind]
    confident: bool
    scores: Dict[str, int] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


def _count(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text))


def _analyte_hits(text: str) -> int:
    """How many lines begin with something a laboratory actually measures.

    This is the strongest lab signal there is, because it is the same lookup
    the parser uses to decide it may compare a value at all.
    """
    hits = 0
    for line in text.splitlines():
        compact = " ".join(line.split())
        if not compact:
            continue
        # The analyte name is whatever precedes the first number.
        head = re.split(r"\d", compact, maxsplit=1)[0].strip(" :.-\t")
        if len(head) >= 3 and resolve_analyte(head):
            hits += 1
    return hits


def classify(text: str) -> Classification:
    """Score the text against each document kind and pick a winner.

    Returns `confident=False` whenever the evidence is thin or two kinds score
    close together. Callers must treat that as "unclear", never as a guess to
    proceed on.
    """
    body = text or ""
    if not body.strip():
        return Classification(None, False, {}, ["Nothing could be read from this file."])

    reasons: List[str] = []

    dose_notation = _count(DOSE_PATTERN, body)
    frequency = _count(_FREQUENCY, body)
    dose_forms = _count(_DOSE_FORM, body)
    directions = _count(_DIRECTIONS, body)
    rx_mark = _count(_RX_MARK, body)
    rx_headings = _count(_PRESCRIPTION_HEADINGS, body)

    prescription = (
        dose_notation * 3
        + min(frequency, 8) * 2
        + min(dose_forms, 8) * 2
        + min(directions, 6) * 2
        + rx_mark * 4
        + min(rx_headings, 4)
    )

    analytes = _analyte_hits(body)
    lab_words = _count(_LAB_VOCABULARY, body)
    ranges = _count(_PRINTED_RANGE, body)
    lab = min(analytes, 20) * 3 + min(lab_words, 10) * 2 + min(ranges, 12)

    modality = _count(_MODALITY, body)
    imaging_words = _count(_IMAGING_VOCABULARY, body)
    imaging = min(modality, 5) * 4 + min(imaging_words, 8) * 2

    # A dose notation on a lab report is a misread; a printed range on a
    # prescription usually is too. Neither is fatal on its own, so the
    # penalty is applied to the loser rather than to the evidence.
    scores = {
        DocumentKind.PRESCRIPTION.value: prescription,
        DocumentKind.LAB_REPORT.value: lab,
        DocumentKind.IMAGING.value: imaging,
    }

    ranked = sorted(scores.items(), key=lambda row: row[1], reverse=True)
    (top_name, top_score), (_, runner_up) = ranked[0], ranked[1]

    if dose_notation:
        reasons.append(f"{dose_notation} dose instruction(s) like 1-0-1")
    if analytes:
        reasons.append(f"{analytes} recognised laboratory test name(s)")
    if modality:
        reasons.append(f"{modality} mention(s) of a scan or X-ray")

    # Thin evidence: too little of anything to be sure what this is.
    if top_score < 6:
        return Classification(
            None, False, scores,
            reasons + ["Too few recognisable markers to tell what this document is."],
        )

    # Two kinds scoring close together is the genuinely dangerous case — a
    # discharge summary quoting both drugs and lab values, for instance. It
    # is better read by a person.
    if top_score - runner_up < max(4, top_score * 0.25):
        return Classification(
            None, False, scores,
            reasons + ["This reads as more than one kind of document at once."],
        )

    return Classification(DocumentKind(top_name), True, scores, reasons)
