"""Parse laboratory report text into structured results, then flag them.

Two stages, both deterministic:

1. `parse_report_text` reads the extracted text line by line and pulls out
   analyte name, value, unit and any reference interval printed on the report.
2. `evaluate` compares each value against a range and assigns a flag.

Range precedence is deliberate: the interval printed on the report always wins,
because it reflects that laboratory's method and units. Built-in ranges are the
fallback, matched on the patient's sex and age. When units disagree and no
conversion is known, the result is recorded with an `unknown` flag rather than
guessed at — a wrong flag on a lab value is worse than no flag.

A language model never decides whether a number is abnormal. It only writes the
narrative summary, downstream, from what this module produced.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.investigations.classification import DOSE_PATTERN
from app.investigations.reference_ranges import (
    QUALITATIVE_EXPECTED,
    UNIT_CONVERSIONS,
    ReferenceRange,
    normalize_unit,
    range_for,
    resolve_analyte,
)
from app.models.enums import AbnormalFlag, Gender

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_NUM = r"\d+(?:[.,]\d+)?"
_VALUE_RE = re.compile(rf"(?P<op>[<>]=?)?\s*(?P<num>{_NUM})")
_RANGE_RE = re.compile(
    rf"(?P<low>{_NUM})\s*(?:-|–|—|to|TO|To)\s*(?P<high>{_NUM})"
)
# A printed date reads as a range to the pattern above: "02-09-2026" is a
# perfectly good "2 to 9". Left unguarded, the header line
# "Patient: Advait  Age: 18/M  Date: 02-09-2026" is parsed as an analyte
# called "Patient Advait Age" measuring 18 against a range of 2-9, and
# flagged HIGH. One nonsense red flag discredits every real one beside it.
_DATE_RE = re.compile(
    # The separator must be the SAME on both sides. Allowing them to
    # differ let "13.0 - 17.0" match as 13 . 0 - 17, which blanked a real
    # haemoglobin range and silently stopped a low value being flagged.
    r"\b\d{1,4}(?P<sep>[-/.])\d{1,2}(?P=sep)\d{2,4}\b"
)

_UPTO_RE = re.compile(rf"(?:up\s*to|upto|<|less than|below)\s*(?P<high>{_NUM})", re.IGNORECASE)
_ATLEAST_RE = re.compile(rf"(?:>|greater than|above|more than)\s*(?P<low>{_NUM})", re.IGNORECASE)

QUALITATIVE_WORDS = {
    "absent", "present", "nil", "negative", "positive", "trace", "reactive",
    "non reactive", "nonreactive", "not detected", "detected", "normal",
    "abnormal", "clear", "turbid", "pale yellow", "yellow", "occasional", "plenty",
    "few", "many", "seen", "not seen",
}

# Lines that are page furniture, not results.
_NOISE_RE = re.compile(
    r"^(page\s*\d|patient\s*(name|id)?\b|name\s*[:.]|ref(erred)?\s*by|"
    r"reg(istration)?\s*no|lab\s*no|uhid|d\.?o\.?b|date\s*[:.]|sex\s*[:.]|"
    r"age\s*[:.]|consultant|"
    r"sample\s*(collected|received)|report(ed)?\s*(on|date)|age\s*/?\s*sex|"
    r"printed\s*on|authorized|verified|end\s*of\s*report|address|phone|"
    r"^-+$|^_+$|^=+$|^\s*$)",
    re.IGNORECASE,
)

# Section headers worth keeping as context.
_SECTION_RE = re.compile(
    r"^(complete blood count|haematology|hematology|biochemistry|liver function|"
    r"kidney function|renal function|lipid profile|thyroid|urine|serology|"
    r"hormone|tumour marker|tumor marker|immunology|microbiology|impression|"
    r"findings|conclusion|advice|comment)",
    re.IGNORECASE,
)


@dataclass
class ParsedResult:
    """One analyte read off the report, before evaluation."""

    raw_line: str
    printed_name: str
    analyte_key: Optional[str] = None
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    operator: Optional[str] = None            # "<" or ">" when the lab reported a bound
    unit: Optional[str] = None
    printed_low: Optional[float] = None
    printed_high: Optional[float] = None
    section: Optional[str] = None


@dataclass
class EvaluatedResult:
    printed_name: str
    analyte_key: Optional[str]
    display_name: str
    value: Optional[float]
    value_text: Optional[str]
    unit: Optional[str]
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    reference_source: str = "none"            # "report" | "builtin" | "none"
    reference_text: Optional[str] = None
    flag: AbnormalFlag = AbnormalFlag.UNKNOWN
    deviation_note: Optional[str] = None
    note: Optional[str] = None
    section: Optional[str] = None
    raw_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["flag"] = self.flag.value
        return payload


@dataclass
class ParsedReport:
    results: List[EvaluatedResult] = field(default_factory=list)
    narrative_lines: List[str] = field(default_factory=list)
    parse_rate: float = 0.0
    # Lines that carried a number but could not be trusted as a measurement.
    # Kept and shown rather than dropped in silence: a doctor who can see
    # that four lines were not understood knows to open the original, where
    # a doctor shown a tidy table of nine rows does not.
    uninterpreted_lines: List[str] = field(default_factory=list)

    @property
    def abnormal(self) -> List[EvaluatedResult]:
        return [
            r for r in self.results
            if r.flag not in (AbnormalFlag.NORMAL, AbnormalFlag.UNKNOWN)
        ]

    @property
    def critical(self) -> List[EvaluatedResult]:
        return [
            r for r in self.results
            if r.flag in (AbnormalFlag.CRITICAL_LOW, AbnormalFlag.CRITICAL_HIGH)
        ]


def _to_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _split_name_and_rest(line: str) -> tuple:
    """Split a result line into its label and the measurement portion."""
    if ":" in line:
        head, _, tail = line.partition(":")
        if head.strip() and not _VALUE_RE.match(head.strip()):
            return head.strip(), tail.strip()
    # Otherwise the label runs until the first number or a run of whitespace.
    match = re.search(rf"(?<!\S)(?:[<>]=?\s*)?{_NUM}(?!\S*[a-zA-Z]{{4,}})", line)
    if match:
        return line[: match.start()].strip(), line[match.start():].strip()
    parts = re.split(r"\s{2,}|\t", line, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return line.strip(), ""


def _extract_unit(segment: str) -> Optional[str]:
    """Pull the unit token that follows the measured value."""
    candidate = re.search(
        r"(?:%|/hpf|/HPF|[a-zA-Zµμ]+(?:\s*/\s*[a-zA-Zµμ.]+)?(?:\s*/\s*[a-zA-Zµμ.]+)?)",
        segment,
    )
    if not candidate:
        return None
    unit = candidate.group(0).strip()
    if unit.lower() in {"to", "and", "or", "upto", "up", "ref", "range", "normal"}:
        return None
    if len(unit) > 20:
        return None
    return unit


def parse_report_text(text: str) -> List[ParsedResult]:
    parsed: List[ParsedResult] = []
    section: Optional[str] = None

    for raw_line in (text or "").splitlines():
        # Keep original spacing: column gaps are the only separator on lines
        # like "Urine Protein        Absent". Collapse only for matching.
        line = raw_line.replace("\u00a0", " ").expandtabs(4).rstrip()
        compact = " ".join(line.split())
        if not compact or _NOISE_RE.match(compact):
            continue

        name, rest = _split_name_and_rest(line)
        looks_like_heading = _SECTION_RE.match(compact) and len(compact) < 60

        if not name or len(name) < 2 or len(name) > 70 or not re.search(r"[a-zA-Z]", name):
            if looks_like_heading:
                section = compact.strip(" :-")
            continue

        result = ParsedResult(raw_line=compact, printed_name=name, section=section)
        result.analyte_key = resolve_analyte(name)

        # Reference interval printed on the report (search the tail only, so the
        # measured value itself is never mistaken for a range bound).
        # Dates are blanked before the range is looked for, rather than the
        # match being rejected afterwards: a line can carry both a real range
        # and a date, and only the date should be ignored.
        rest_for_range = _DATE_RE.sub(lambda m: " " * len(m.group(0)), rest)
        # Indian dose notation is the other thing that reads as an interval.
        # "PAN 40 MG 1-0-1" is one tablet in the morning and one at night,
        # and was parsed as pantoprazole measuring 40 against a range of
        # 1.0 to 0.0 — then flagged HIGH, on a prescription.
        rest_for_range = DOSE_PATTERN.sub(
            lambda m: " " * len(m.group(0)), rest_for_range
        )

        range_match = _RANGE_RE.search(rest_for_range)
        measurement_zone = rest
        if range_match:
            low = _to_float(range_match.group("low"))
            high = _to_float(range_match.group("high"))
            # An interval whose top is not above its bottom is not an
            # interval. "1.0 - 0.0" reached the doctor's screen as a range
            # that every possible value exceeds; whatever those digits were,
            # they were not a reference range, so they are discarded rather
            # than used to flag anything.
            if low is not None and high is not None and high > low:
                result.printed_low = low
                result.printed_high = high
                measurement_zone = rest[: range_match.start()]
        else:
            upto = _UPTO_RE.search(rest)
            atleast = _ATLEAST_RE.search(rest)
            if upto and upto.start() > 0:
                result.printed_high = _to_float(upto.group("high"))
                measurement_zone = rest[: upto.start()]
            elif atleast and atleast.start() > 0:
                result.printed_low = _to_float(atleast.group("low"))
                measurement_zone = rest[: atleast.start()]

        value_match = _VALUE_RE.search(measurement_zone)
        if value_match:
            result.value_numeric = _to_float(value_match.group("num"))
            result.operator = value_match.group("op")
            result.unit = _extract_unit(measurement_zone[value_match.end():])
        else:
            lowered = measurement_zone.lower().strip(" .")
            for word in sorted(QUALITATIVE_WORDS, key=len, reverse=True):
                if lowered.startswith(word):
                    result.value_text = measurement_zone.strip(" .")
                    break
            if result.value_text is None:
                # No measurement on this line. Only now may it be a heading.
                if looks_like_heading:
                    section = compact.strip(" :-")
                continue

        parsed.append(result)

    return parsed


def _convert(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    if not from_unit or not to_unit or from_unit == to_unit:
        return value
    factor = UNIT_CONVERSIONS.get((from_unit, to_unit))
    return value * factor if factor is not None else None


def _flag_numeric(
    value: float,
    low: Optional[float],
    high: Optional[float],
    reference: Optional[ReferenceRange],
) -> tuple:
    """Return (flag, deviation note)."""
    if reference is not None:
        if reference.critical_low is not None and value <= reference.critical_low:
            return AbnormalFlag.CRITICAL_LOW, f"critically low (<= {reference.critical_low})"
        if reference.critical_high is not None and value >= reference.critical_high:
            return AbnormalFlag.CRITICAL_HIGH, f"critically high (>= {reference.critical_high})"
    if low is not None and value < low:
        gap = round((low - value) / low * 100) if low else None
        return AbnormalFlag.LOW, f"{gap}% below the lower limit" if gap else "below range"
    if high is not None and value > high:
        gap = round((value - high) / high * 100) if high else None
        return AbnormalFlag.HIGH, f"{gap}% above the upper limit" if gap else "above range"
    if low is None and high is None:
        return AbnormalFlag.UNKNOWN, None
    return AbnormalFlag.NORMAL, None


def evaluate(
    parsed: List[ParsedResult],
    *,
    sex: Optional[Gender] = None,
    age: Optional[int] = None,
) -> List[EvaluatedResult]:
    evaluated: List[EvaluatedResult] = []

    for item in parsed:
        reference = (
            range_for(item.analyte_key, sex=sex, age=age) if item.analyte_key else None
        )
        display = reference.analyte if reference else item.printed_name
        result = EvaluatedResult(
            printed_name=item.printed_name,
            analyte_key=item.analyte_key,
            display_name=display,
            value=item.value_numeric,
            value_text=item.value_text,
            unit=item.unit,
            section=item.section,
            raw_line=item.raw_line,
            note=reference.note if reference else None,
        )

        # --- qualitative result ---
        if item.value_numeric is None:
            expected = QUALITATIVE_EXPECTED.get(item.analyte_key or "", [])
            answer = (item.value_text or "").strip().lower()
            if expected:
                result.reference_source = "builtin"
                result.reference_text = " / ".join(expected)
                normalised = answer.replace("-", " ").strip(" .")
                result.flag = (
                    AbnormalFlag.NORMAL
                    if any(normalised.startswith(option) for option in expected)
                    else AbnormalFlag.ABNORMAL
                )
            else:
                result.flag = AbnormalFlag.UNKNOWN
            evaluated.append(result)
            continue

        # --- numeric result: the report's own interval wins ---
        low, high, source = item.printed_low, item.printed_high, "none"
        if low is not None or high is not None:
            source = "report"
        else:
            if reference is not None:
                unit_printed = normalize_unit(item.unit)
                unit_reference = normalize_unit(reference.unit)
                if not unit_printed or unit_printed == unit_reference:
                    low, high, source = reference.low, reference.high, "builtin"
                else:
                    converted_low = (
                        _convert(reference.low, unit_reference, unit_printed)
                        if reference.low is not None else None
                    )
                    converted_high = (
                        _convert(reference.high, unit_reference, unit_printed)
                        if reference.high is not None else None
                    )
                    if converted_low is not None or converted_high is not None:
                        low, high, source = converted_low, converted_high, "builtin"
                    else:
                        # Units disagree and no conversion is known: record the
                        # value, refuse to flag it.
                        result.flag = AbnormalFlag.UNKNOWN
                        result.note = (
                            f"Reported in {item.unit}; built-in range is in "
                            f"{reference.unit}. Not compared."
                        )
                        evaluated.append(result)
                        continue

        result.reference_low = low
        result.reference_high = high
        result.reference_source = source
        if low is not None and high is not None:
            result.reference_text = f"{low} - {high}"
        elif high is not None:
            result.reference_text = f"up to {high}"
        elif low is not None:
            result.reference_text = f"above {low}"

        # Critical thresholds are absolute numbers, so they may only be
        # applied when we know they are in the same units as the value. When
        # the report printed its own range we have not reconciled anything:
        # the range is the laboratory's, the thresholds are ours, and a
        # platelet count of 145000 /cmm was called critically high against a
        # ceiling of 10.0 lakh/cumm. Comparing against the printed range is
        # still right; only the critical layer is withheld.
        critical_reference = None
        if reference is not None:
            if source == "builtin":
                critical_reference = reference
            elif source == "report":
                unit_printed = normalize_unit(item.unit)
                unit_reference = normalize_unit(reference.unit)
                if unit_printed and unit_printed == unit_reference:
                    critical_reference = reference

        flag, deviation = _flag_numeric(
            item.value_numeric, low, high, critical_reference,
        )
        result.flag = flag
        result.deviation_note = deviation
        evaluated.append(result)

    return evaluated


def is_trustworthy(result: EvaluatedResult) -> bool:
    """May this row be shown to a doctor as a measured value?

    Only on one of two grounds: the test is one we recognise, so we know what
    it is and what it should be; or the report printed its own reference
    interval beside it, so the comparison is the laboratory's and not ours.

    Everything else is a line with a number on it. On a genuine lab report
    that is the registration number and the page footer. On a prescription
    read by mistake it is the entire document, which is how "Regd No. 24294"
    and "min 812 Meg" came to sit in a table headed Results.
    """
    if result.analyte_key:
        return True
    return result.reference_source == "report" and (
        result.reference_low is not None or result.reference_high is not None
    )


def analyze_text(
    text: str, *, sex: Optional[Gender] = None, age: Optional[int] = None
) -> ParsedReport:
    """Full deterministic pass over one report's text."""
    parsed = parse_report_text(text)
    evaluated = evaluate(parsed, sex=sex, age=age)

    results = [item for item in evaluated if is_trustworthy(item)]
    uninterpreted = [
        item.raw_line for item in evaluated
        if not is_trustworthy(item) and item.raw_line
    ]
    recognised = sum(1 for r in results if r.analyte_key)
    narrative = [
        line.strip()
        for line in (text or "").splitlines()
        if re.match(r"^\s*(impression|findings|conclusion|advice|comment|opinion)",
                    line.strip(), re.IGNORECASE)
    ]
    return ParsedReport(
        results=results,
        narrative_lines=narrative,
        parse_rate=round(recognised / len(results), 2) if results else 0.0,
        uninterpreted_lines=uninterpreted[:40],
    )
