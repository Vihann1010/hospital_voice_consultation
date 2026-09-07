"""Turn a doctor's dictation into structured medicine lines.

"Tablet Paracetamol 650 mg SOS. Tablet Pantoprazole 40 mg before breakfast."
becomes two structured rows with form, drug, strength, frequency, timing and
duration separated out.

Deterministic first: dictated prescriptions are highly patterned, so regex
handles the well-formed majority at zero cost and zero latency. Whatever fails
to parse is handed to the LLM stage (`app/ai/pipeline/dictation_parser.py`),
and every row — however it was produced — is reconciled against the formulary
so the doctor edits a real drug rather than a transcription artefact.

Nothing here is ever auto-prescribed: the parsed rows populate an editable
form that the doctor must confirm.
"""
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.prescriptions.formulary import Medicine, match_by_name

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
FORMS: Dict[str, str] = {
    "tablet": "Tablet", "tab": "Tablet", "tabs": "Tablet",
    "capsule": "Capsule", "cap": "Capsule", "caps": "Capsule",
    "syrup": "Syrup", "syp": "Syrup", "suspension": "Syrup",
    "injection": "Injection", "inj": "Injection",
    "ointment": "Ointment", "cream": "Ointment", "gel": "Ointment",
    "drops": "Drops", "drop": "Drops",
    "sachet": "Sachet", "powder": "Sachet",
    "spray": "Spray", "inhaler": "Inhaler",
    "pessary": "Pessary", "suppository": "Suppository",
}

# Canonical frequency code -> (spoken forms, human label, doses per day)
FREQUENCIES: List[Tuple[str, List[str], str, Optional[float]]] = [
    ("OD",   ["od", "once daily", "once a day", "one time a day", "daily", "1-0-0", "0-0-1"],
     "Once a day", 1),
    ("BD",   ["bd", "bid", "twice daily", "twice a day", "two times a day", "1-0-1"],
     "Twice a day", 2),
    ("TDS",  ["tds", "tid", "thrice daily", "three times a day", "thrice a day", "1-1-1"],
     "Three times a day", 3),
    ("QID",  ["qid", "qds", "four times a day"], "Four times a day", 4),
    ("HS",   ["hs", "at bedtime", "at night", "night", "bedtime", "0-0-1 at night"],
     "At bedtime", 1),
    ("SOS",  ["sos", "as needed", "if required", "when required", "prn", "if needed"],
     "Only when needed", None),
    ("STAT", ["stat", "immediately", "at once", "single dose", "one dose"], "Single dose now", None),
    ("WEEKLY", ["once weekly", "once a week", "weekly", "every week"], "Once a week", None),
    ("ALT",  ["alternate day", "alternate days", "every other day", "eod"],
     "On alternate days", None),
    ("Q4H",  ["every four hours", "every 4 hours", "q4h"], "Every 4 hours", 6),
    ("Q6H",  ["every six hours", "every 6 hours", "q6h"], "Every 6 hours", 4),
    ("Q8H",  ["every eight hours", "every 8 hours", "q8h"], "Every 8 hours", 3),
]

TIMINGS: List[Tuple[List[str], str]] = [
    (["before breakfast"], "Before breakfast"),
    (["after breakfast"], "After breakfast"),
    (["before lunch"], "Before lunch"),
    (["after lunch"], "After lunch"),
    (["before dinner"], "Before dinner"),
    (["after dinner"], "After dinner"),
    (["empty stomach", "on an empty stomach"], "On an empty stomach"),
    (["before food", "before meals", "before meal"], "Before food"),
    (["after food", "after meals", "after meal", "with food"], "After food"),
    (["at bedtime", "before sleeping", "before bed"], "At bedtime"),
    (["in the morning", "morning"], "In the morning"),
    (["in the evening", "evening"], "In the evening"),
    (["per vaginam", "vaginally", "pv"], "Per vaginam"),
    (["locally", "apply locally", "external use"], "Apply locally"),
]

ROUTES = {
    "orally": "Oral", "oral": "Oral", "by mouth": "Oral",
    "intravenous": "IV", "iv": "IV", "intramuscular": "IM", "im": "IM",
    "subcutaneous": "SC", "topical": "Topical", "per vaginam": "Vaginal",
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14,
    "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90,
    "half": 0.5, "a": 1, "an": 1,
}

_STRENGTH_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|µg|ug|g|gm|ml|iu|units?|%)\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"(?:for|x|×|over)?\s*(?P<count>\d+|" + "|".join(NUMBER_WORDS) + r")\s*"
    r"(?P<unit>day|days|week|weeks|month|months|year|years)\b",
    re.IGNORECASE,
)
_CONTINUE_RE = re.compile(r"\b(continue|continuously|long term|lifelong|till review|until review)\b",
                          re.IGNORECASE)
_QUANTITY_RE = re.compile(
    r"\b(?P<count>\d+(?:\.\d+)?|half|one|two|three|four)\s*(?:tab|tabs|tablet|tablets|"
    r"cap|caps|capsule|capsules|spoon|spoons|teaspoon|tsp|ml)\b",
    re.IGNORECASE,
)

# A dictation is split on these before parsing each medicine.
_SPLIT_RE = re.compile(
    r"(?:\.|;|\n|,?\s+(?:and\s+)?(?:then\s+)?(?=(?:tablet|tab|capsule|cap|syrup|syp|injection|inj|"
    r"ointment|cream|gel|drops|sachet|spray|inhaler|pessary|suppository)\b))",
    re.IGNORECASE,
)

_NOISE_PREFIX = re.compile(
    r"^(?:next|also|please|and|then|start|give|add|prescribe|write|number\s*\d+|\d+[.)])\s+",
    re.IGNORECASE,
)


@dataclass
class DictatedMedicine:
    raw_text: str
    name: str = ""
    formulary_code: Optional[str] = None
    generic: Optional[str] = None
    form: Optional[str] = None
    strength: Optional[str] = None
    dosage: Optional[str] = None
    frequency_code: Optional[str] = None
    frequency_text: Optional[str] = None
    duration: Optional[str] = None
    timing: Optional[str] = None
    route: Optional[str] = None
    instructions: Optional[str] = None
    confidence: float = 0.0
    unmatched: bool = False
    substituted: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _find_frequency(text: str) -> Tuple[Optional[str], Optional[str], str]:
    """Return (code, label, text with the phrase removed). Longest match wins."""
    candidates = []
    for code, spoken_forms, label, _ in FREQUENCIES:
        for phrase in spoken_forms:
            pattern = re.compile(rf"(?<![a-zA-Z0-9]){re.escape(phrase)}(?![a-zA-Z])",
                                 re.IGNORECASE)
            match = pattern.search(text)
            if match:
                candidates.append((len(phrase), code, label, match.span()))
    if not candidates:
        return None, None, text
    candidates.sort(reverse=True)
    _, code, label, (start, end) = candidates[0]
    return code, label, (text[:start] + " " + text[end:])


def _find_timing(text: str) -> Tuple[Optional[str], str]:
    candidates = []
    for phrases, label in TIMINGS:
        for phrase in phrases:
            match = re.search(rf"(?<![a-zA-Z]){re.escape(phrase)}(?![a-zA-Z])", text, re.IGNORECASE)
            if match:
                candidates.append((len(phrase), label, match.span()))
    if not candidates:
        return None, text
    candidates.sort(reverse=True)
    _, label, (start, end) = candidates[0]
    return label, (text[:start] + " " + text[end:])


def _find_duration(text: str) -> Tuple[Optional[str], str]:
    if _CONTINUE_RE.search(text):
        cleaned = _CONTINUE_RE.sub(" ", text)
        return "Continue", cleaned
    match = _DURATION_RE.search(text)
    if not match:
        return None, text
    raw_count = match.group("count").lower()
    count = NUMBER_WORDS.get(raw_count)
    if count is None:
        try:
            count = float(raw_count)
        except ValueError:
            return None, text
    count_display = int(count) if float(count).is_integer() else count
    unit = match.group("unit").lower().rstrip("s")
    plural = "" if count_display == 1 else "s"
    return f"{count_display} {unit}{plural}", text[: match.start()] + " " + text[match.end():]


def _find_strength(text: str) -> Tuple[Optional[str], str]:
    match = _STRENGTH_RE.search(text)
    if not match:
        return None, text
    unit = match.group("unit").lower()
    unit = {"gm": "g", "ug": "mcg", "µg": "mcg", "unit": "IU", "units": "IU",
            "iu": "IU"}.get(unit, unit)
    return (
        f"{match.group('value')} {unit}".strip(),
        text[: match.start()] + " " + text[match.end():],
    )


def _find_form(text: str) -> Tuple[Optional[str], str]:
    for spoken, canonical in sorted(FORMS.items(), key=lambda kv: -len(kv[0])):
        match = re.search(rf"(?<![a-zA-Z]){re.escape(spoken)}(?![a-zA-Z])", text, re.IGNORECASE)
        if match:
            return canonical, text[: match.start()] + " " + text[match.end():]
    return None, text


def _find_route(text: str) -> Tuple[Optional[str], str]:
    for spoken, canonical in sorted(ROUTES.items(), key=lambda kv: -len(kv[0])):
        match = re.search(rf"(?<![a-zA-Z]){re.escape(spoken)}(?![a-zA-Z])", text, re.IGNORECASE)
        if match:
            return canonical, text[: match.start()] + " " + text[match.end():]
    return None, text


def _find_quantity(text: str) -> Tuple[Optional[str], str]:
    match = _QUANTITY_RE.search(text)
    if not match:
        return None, text
    return match.group(0).strip(), text[: match.start()] + " " + text[match.end():]


def split_dictation(transcript: str) -> List[str]:
    """Split a spoken prescription into one segment per medicine."""
    text = " ".join((transcript or "").split())
    if not text:
        return []
    segments = [segment.strip(" ,;.") for segment in _SPLIT_RE.split(text)]
    return [segment for segment in segments if segment and len(segment) > 2]


def parse_segment(segment: str) -> DictatedMedicine:
    """Pull structure out of one dictated medicine line."""
    result = DictatedMedicine(raw_text=segment.strip())
    working = _NOISE_PREFIX.sub("", segment.strip())

    result.form, working = _find_form(working)
    result.strength, working = _find_strength(working)
    result.frequency_code, result.frequency_text, working = _find_frequency(working)
    result.timing, working = _find_timing(working)
    result.duration, working = _find_duration(working)
    result.route, working = _find_route(working)
    result.dosage, working = _find_quantity(working)

    # Whatever survives should be the drug name plus any free instruction.
    leftover = " ".join(working.replace(",", " ").split())
    leftover = re.sub(r"^\s*(?:of|the)\s+", "", leftover, flags=re.IGNORECASE)

    name_part, instruction_part = leftover, ""
    for marker in (" with ", " if ", " when ", " for ", " to ", " and "):
        index = leftover.lower().find(marker)
        if index > 0:
            name_part, instruction_part = leftover[:index], leftover[index:]
            break

    result.name = name_part.strip(" -.,").title() if name_part.strip() else ""
    if instruction_part.strip():
        result.instructions = instruction_part.strip(" -.,")

    # Some frequency phrases carry their own timing ("HS" means at bedtime).
    # The frequency matcher consumed the phrase, so restore the implication
    # before formulary defaults get a chance to fill the gap with something else.
    if result.timing is None:
        if result.frequency_code == "HS":
            result.timing = "At bedtime"
        elif result.frequency_code == "STAT":
            result.timing = "Now"

    # Reconcile against the formulary.
    dictated_name = result.name
    matched: Optional[Medicine] = match_by_name(result.name) if result.name else None
    if matched is not None:
        result.formulary_code = matched.code
        result.generic = ", ".join(matched.ingredients)
        result.name = matched.name
        if not result.form:
            result.form = matched.form
        if not result.strength and len(matched.strengths) == 1:
            result.strength = matched.strengths[0]
        if not result.frequency_code and matched.default_frequency:
            result.frequency_text = matched.default_frequency
        if not result.timing and matched.default_timing:
            result.timing = matched.default_timing.capitalize()
        if matched.note:
            result.warnings.append(matched.note)
        # A loose match means the dictated word was resolved to a different
        # product ("Calcium" -> "Calcimax"). That is a helpful prefill, but the
        # doctor must see that a substitution happened.
        spoken = dictated_name.strip().lower()
        resolved = matched.name.strip().lower()
        if spoken and spoken not in resolved and resolved not in spoken:
            result.warnings.append(
                f"Dictated as \"{dictated_name}\" and interpreted as \"{matched.name}\" — confirm."
            )
            result.substituted = True
    else:
        result.unmatched = True
        if result.name:
            result.warnings.append(
                "Not found in the hospital formulary — please confirm the drug name."
            )

    # Confidence reflects how much structure was recovered, so the UI can
    # highlight rows that need a second look.
    score = 0.0
    if result.name:
        score += 0.35
    if matched is not None:
        score += 0.25
    if result.strength:
        score += 0.15
    if result.frequency_code or result.frequency_text:
        score += 0.15
    if result.form:
        score += 0.10
    if result.substituted:
        score -= 0.30     # a substituted name always deserves a second look
    result.confidence = round(max(min(score, 1.0), 0.0), 2)
    return result


def parse_dictation(transcript: str) -> List[DictatedMedicine]:
    return [parse_segment(segment) for segment in split_dictation(transcript)]


def needs_llm_assistance(medicines: List[DictatedMedicine]) -> bool:
    """True when the deterministic pass did poorly enough to warrant the model."""
    if not medicines:
        return True
    weak = sum(1 for medicine in medicines if medicine.confidence < 0.6)
    return weak / len(medicines) > 0.4
