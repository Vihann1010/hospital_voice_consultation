"""Read a radiology report by quoting it, not by interpreting it.

An imaging report already contains its own conclusion, written by a
radiologist who looked at the film. There is nothing for this system to add
and a great deal it could get wrong: the numbers on an ultrasound are
measurements in millimetres with no reference range on the page, and a
paraphrase of "no acute intracranial abnormality" that drops the word "acute"
is a different sentence about a different patient.

So this module extracts the impression verbatim and stops. No values are
compared, no flags are raised, and no summary is generated. If there is no
impression block to quote, the report is unclear and says so.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Ordered by how conclusive each heading is: a report carrying both FINDINGS
# and IMPRESSION should be quoted from the impression.
_CONCLUSION_HEADINGS = (
    "impression", "conclusion", "opinion", "summary",
)
_DETAIL_HEADINGS = ("findings", "observations", "report")
_STOP_HEADINGS = (
    "advice", "suggestion", "recommendation", "note", "disclaimer",
    "technique", "clinical history", "indication", "comparison",
    "referred by", "radiologist", "signature",
)

_MODALITY = re.compile(
    r"\b(x[\s-]?ray|xray|radiograph|mri|magnetic\s+resonance|ct\s*scan|"
    r"computed\s+tomography|usg|ultraso(?:und|nography)|sonograph[yi]|doppler|"
    r"mammogra(?:m|phy)|echocardiogra(?:m|phy)|dexa|pet\s*ct)\b",
    re.IGNORECASE,
)


_ALL_HEADINGS = _CONCLUSION_HEADINGS + _DETAIL_HEADINGS + _STOP_HEADINGS

# "IMPRESSION", "IMPRESSION:", "IMPRESSION : text", "Impression - text".
# The separator is required when text follows, so that "Findings suggestive
# of cholelithiasis" stays prose instead of opening a Findings section.
_HEADING_RE = re.compile(
    r"^\s*(?P<heading>" + "|".join(re.escape(h) for h in _ALL_HEADINGS) + r")"
    r"\s*(?:[:.\-]\s*(?P<rest>.*)|\s*)$",
    re.IGNORECASE,
)

# The report ends where the signature begins. Without this the reporting
# doctor's name and credentials were quoted to the reading doctor as part of
# the impression.
_SIGNATURE_RE = re.compile(
    r"^\s*(?:dr\.?\s|prof\.?\s)"
    r"|\b(?:radiologist|pathologist|sonologist|consultant|"
    r"m\.?b\.?b\.?s|m\.?d\b|d\.?m\.?r\.?d|d\.?n\.?b|"
    r"signature|verified\s+by|reported\s+by|electronically\s+signed|"
    r"end\s+of\s+report)\b",
    re.IGNORECASE,
)


def _heading_of(line: str) -> Tuple[Optional[str], str]:
    """The section this line opens and whatever followed it on the same line.

    A heading is the word alone on its line, or the word followed by a
    separator. "Findings suggestive of cholelithiasis" is prose that happens
    to begin with a heading word and opens nothing.

    Returns (None, line) when the line opens no section.
    """
    compact = " ".join(line.split())
    match = _HEADING_RE.match(compact)
    if not match:
        return None, compact
    return match.group("heading").lower(), (match.group("rest") or "").strip()


@dataclass
class ImagingReading:
    modality: Optional[str] = None
    impression: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)

    @property
    def confident(self) -> bool:
        """Only an impression counts. Findings alone are a description, not a
        conclusion, and quoting them as though they were one overstates the
        report."""
        return bool(self.impression)

    def to_dict(self) -> Dict[str, object]:
        return {
            "modality": self.modality,
            "impression": self.impression,
            "findings": self.findings,
        }


def read_imaging(text: str) -> ImagingReading:
    """Quote the radiologist's own conclusion. Nothing is interpreted."""
    reading = ImagingReading()

    modality = _MODALITY.search(text or "")
    if modality:
        reading.modality = " ".join(modality.group(0).split()).upper()

    current: Optional[str] = None
    for raw_line in (text or "").splitlines():
        line = " ".join(raw_line.replace(" ", " ").split())
        if not line:
            continue

        heading, rest = _heading_of(line)
        if heading is not None:
            current = heading
            if not rest:
                continue
            line = rest

        # A signature ends the report wherever it appears.
        if _SIGNATURE_RE.search(line):
            current = None
            continue

        if current in _CONCLUSION_HEADINGS:
            reading.impression.append(line)
        elif current in _DETAIL_HEADINGS:
            reading.findings.append(line)
        # Anything under a stop heading, or above every heading, is letterhead
        # and clinical history. Neither is the radiologist's conclusion.

    return reading
