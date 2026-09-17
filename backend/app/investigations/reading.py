"""Decide how one uploaded document may be read, and read it that way.

This module exists to hold a single rule in a single place: nothing reaches
the doctor's screen as a finding unless we can say why it is trustworthy.
Everything else is reported as unclear, by name, with the original one tap
away.

Three analysers, and they are not interchangeable:

  lab report    values compared arithmetically against reference ranges
  prescription  medicines and problems, matched against the formulary
  imaging       the radiologist's own impression, quoted verbatim

Running the wrong one is not a near miss. A prescription read by the
laboratory parser produced an analyte called PAN measuring 40 against a
reference range of 1.0 to 0.0, flagged HIGH — the range was the dose
instruction "1-0-0" and the analyte was pantoprazole. So the kind declared at
upload is checked against a classification of the text itself, and the two
have to agree before anything is analysed at all.

The asymmetry between the analysers is deliberate. Numeric flagging needs
positive corroboration, because a wrong flag is an assertion about a
measurement nobody made. Quoting a radiologist and matching a drug name
against the formulary are self-limiting: they produce nothing unless they
recognise something, so they may run on the declaration alone.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.investigations.classification import classify
from app.investigations.imaging_reading import read_imaging
from app.investigations.parsing import analyze_text
from app.investigations.prescription_reading import read_prescription
from app.models.enums import DocumentKind, Gender

# What the doctor is told when we will not stand behind the contents. The
# wording is deliberately the same everywhere: one sentence, no hedging, and
# an instruction rather than an apology.
UNCLEAR_HEADLINE = "Report unclear — please go through it manually."

_KIND_LABEL = {
    DocumentKind.PRESCRIPTION: "a prescription",
    DocumentKind.LAB_REPORT: "a laboratory report",
    DocumentKind.IMAGING: "a scan or X-ray report",
    DocumentKind.OTHER: "something else",
}


@dataclass
class Reading:
    """The analysis of one document, and whether it may be believed."""

    analysis: Dict[str, Any]
    #: Only a clear laboratory report earns a written narrative. Everything
    #: else is either quoted verbatim or reported as unclear, and neither
    #: needs a language model.
    should_summarise: bool = False


def _base(
    *,
    declared: Optional[DocumentKind],
    detected: Optional[DocumentKind],
    confident: bool,
    reasons: list,
    extraction: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "extraction": extraction,
        "declared_kind": declared.value if declared else None,
        "detected_kind": detected.value if detected else None,
        "detection_confident": confident,
        "detection_reasons": reasons,
        "document_kind": None,
        "clarity": "unclear",
        "unclear_reason": None,
        # Always present, so every existing consumer of an analysis — the
        # list rows, the order-item matcher — keeps working for kinds that
        # have no measured values at all.
        "results": [],
        "abnormal": [],
        "critical": [],
        "abnormal_count": 0,
        "critical_count": 0,
    }


def _unclear(analysis: Dict[str, Any], reason: str) -> Reading:
    analysis["clarity"] = "unclear"
    analysis["unclear_reason"] = reason
    analysis["summary"] = {
        "headline": UNCLEAR_HEADLINE,
        "doctor_summary": reason,
        "key_findings": [],
        "patterns_noticed": [],
        "suggested_next_steps": [],
        "unreadable": True,
        "disclaimer": (
            "Nothing on this document has been interpreted. Open the original."
        ),
    }
    return Reading(analysis, should_summarise=False)


def read_document(
    text: str,
    *,
    declared: Optional[DocumentKind],
    extraction: Dict[str, Any],
    legible: bool,
    sex: Optional[Gender] = None,
    age: Optional[int] = None,
) -> Reading:
    """Analyse one document, or explain why it was not analysed."""
    detection = classify(text)
    analysis = _base(
        declared=declared,
        detected=detection.kind,
        confident=detection.confident,
        reasons=list(detection.reasons),
        extraction=extraction,
    )

    # --- the page was never readable in the first place -------------------
    if not legible:
        return _unclear(
            analysis,
            "This looks like a handwritten page or a photograph that optical "
            "character recognition could not turn into text. Nothing on it has "
            "been read or checked.",
        )

    # --- the declaration and the page disagree ----------------------------
    if (
        declared is not None
        and declared is not DocumentKind.OTHER
        and detection.confident
        and detection.kind is not declared
    ):
        return _unclear(
            analysis,
            f"This was uploaded as {_KIND_LABEL[declared]}, but it reads as "
            f"{_KIND_LABEL[detection.kind]}. Because the two disagree, nothing "
            "on it has been interpreted.",
        )

    kind = declared if declared not in (None, DocumentKind.OTHER) else detection.kind

    if kind is None:
        return _unclear(
            analysis,
            "It was not possible to tell what kind of document this is — "
            + (detection.reasons[-1] if detection.reasons else "too little was legible.")
            + " Nothing on it has been interpreted.",
        )

    analysis["document_kind"] = kind.value

    # --- laboratory report -------------------------------------------------
    if kind is DocumentKind.LAB_REPORT:
        # A number gets a flag only when the page corroborates that it is a
        # laboratory report. The declaration alone is not enough: it is one
        # tap on a phone, and the cost of being wrong is an invented
        # abnormal result.
        if not detection.confident or detection.kind is not DocumentKind.LAB_REPORT:
            return _unclear(
                analysis,
                "This was uploaded as a laboratory report, but not enough of it "
                "reads like one to compare any value against a reference range. "
                "No values have been flagged.",
            )

        parsed = analyze_text(text, sex=sex, age=age)
        analysis["results"] = [item.to_dict() for item in parsed.results]
        analysis["abnormal"] = [item.to_dict() for item in parsed.abnormal]
        analysis["critical"] = [item.to_dict() for item in parsed.critical]
        analysis["abnormal_count"] = len(parsed.abnormal)
        analysis["critical_count"] = len(parsed.critical)
        analysis["recognised_rate"] = parsed.parse_rate
        analysis["narrative_lines"] = parsed.narrative_lines
        analysis["uninterpreted_lines"] = parsed.uninterpreted_lines

        if not parsed.results:
            return _unclear(
                analysis,
                "No line on this report could be read as a test with a value and "
                "a range, so nothing has been compared. "
                f"{len(parsed.uninterpreted_lines)} line(s) carried numbers that "
                "could not be interpreted.",
            )

        analysis["clarity"] = "clear"
        return Reading(analysis, should_summarise=True)

    # --- prescription ------------------------------------------------------
    if kind is DocumentKind.PRESCRIPTION:
        reading = read_prescription(text)
        analysis["prescription"] = reading.to_dict()
        if not reading.confident:
            return _unclear(
                analysis,
                "No medicine on this page matched a known drug and no diagnosis "
                "was written in a form that could be read. Nothing has been "
                "interpreted.",
            )
        analysis["clarity"] = "clear"
        # Partly read is still read: the medicines that matched are stated,
        # and the lines that did not are shown as they were printed.
        analysis["needs_manual_check"] = reading.needs_manual_check
        return Reading(analysis, should_summarise=False)

    # --- imaging -----------------------------------------------------------
    if kind is DocumentKind.IMAGING:
        reading = read_imaging(text)
        analysis["imaging"] = reading.to_dict()
        if not reading.confident:
            return _unclear(
                analysis,
                "No impression or conclusion could be found on this scan report, "
                "and the findings alone are not a conclusion. Nothing has been "
                "interpreted.",
            )
        analysis["clarity"] = "clear"
        return Reading(analysis, should_summarise=False)

    # --- anything else -----------------------------------------------------
    # A discharge summary, an insurance letter, a photograph of a pill packet.
    # The file is stored and openable; there is no analyser for it and
    # pretending otherwise is the failure this module exists to prevent.
    analysis["clarity"] = "not_analysed"
    analysis["unclear_reason"] = (
        "This is not a prescription, a laboratory report or a scan report, so "
        "there is nothing to read from it automatically. The file is attached."
    )
    return Reading(analysis, should_summarise=False)
