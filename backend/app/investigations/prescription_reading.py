"""Read an old prescription: what the patient is on, and what for.

A prescription carries no measurements, so nothing here is compared against
anything. The output is a list of medicines and a list of problems, and the
only question that matters for each is whether it is certain enough to put in
front of a doctor as fact.

The rule is that a medicine appears by name only when that name matched the
formulary exactly. OCR on a photograph of a printed prescription reliably
produces "Gobapantin" for Gabapentin and "ETOSHINE SOMO TAMET" for Etoshine
90 mg, and a screen that states either as the patient's current medication is
worse than a screen that shows nothing: the doctor cannot tell which words
were read and which were guessed.

So there are three lists, not one. An exact match is a medicine and is stated
as fact. A near match is not — it goes to `possible_medicines`, where the line
is shown exactly as printed and the formulary name appears only as something
to check. Anything carrying dosing that matches nothing goes to
`unidentified_lines`, also verbatim. The doctor is told to read the original
whenever either of those two lists has anything in it.

No language model runs over any of this. Every field below is either lifted
verbatim from the page or resolved against the formulary shipped in code.
"""
import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.ai.pipeline.medication_rules import BRAND_INGREDIENTS, normalize_name
from app.prescriptions import formulary

# How similar a token must be to a formulary name before it is offered as a
# possible misreading of it. Measured, not guessed: "gobapantin" (real OCR
# output for gabapentin) scores exactly 0.80, and across a probe of drugs
# deliberately absent from the formulary — etodolac, nimesulide, torsemide,
# clobazam, cilnidipine, febuxostat and others — 0.80 produced no suggestion
# at all. Raising it loses a real misreading; lowering it starts inventing.
_FUZZY_CUTOFF = 0.80

# Strength and dose text clinging to the matched token: "PAN 40" matches
# pantoprazole, but reporting it as read as "PAN 40" reads like a dose.
_TOKEN_TAIL = re.compile(r"[\s\d.,]+(?:mg|mcg|g|gm|ml|iu)?\s*$", re.IGNORECASE)

# Words that appear beside a drug name and are not part of it.
_LEADING_NOISE = re.compile(
    r"^\s*(?:\d+[.)]\s*|[-*•]\s*|"
    r"(?:tab|tabs|tablet|cap|caps|capsule|syp|syrup|susp|inj|injection|"
    r"ointment|cream|gel|drops?|sachet|lotion|spray|inhaler)\b\.?\s*)+",
    re.IGNORECASE,
)

_STRENGTH = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|gm|ml|iu|units?|%)\b", re.IGNORECASE
)
from app.investigations.classification import DOSE_PATTERN as _DOSE_NOTATION
_FREQUENCY = re.compile(
    r"\b(OD|BD|BID|TDS|TID|QID|QDS|HS|SOS|STAT|PRN|OW)\b", re.IGNORECASE
)
_DURATION = re.compile(
    r"\b(?:x\s*)?(\d+)\s*(day|days|week|weeks|month|months)\b", re.IGNORECASE
)
_TIMING = re.compile(
    r"\b(after\s+food|before\s+food|after\s+meals?|before\s+meals?|"
    r"empty\s+stomach|at\s+bedtime|bedtime|with\s+water)\b",
    re.IGNORECASE,
)

# Headings that introduce the patient's problems rather than their drugs.
_PROBLEM_HEADING = re.compile(
    r"^\s*(?:provisional\s+diagnosis|diagnosis|dx|impression|c\s*/\s*o|"
    r"complaints?|chief\s+complaints?|k\s*/\s*c\s*/\s*o|known\s+case\s+of|"
    r"h\s*/\s*o|history\s+of|indication)\s*[:.\-]\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

# Page furniture on a clinic letterhead.
_FURNITURE = re.compile(
    r"^\s*(?:page\s*\d|regd?\.?\s*(?:no|office)|reg(?:istration)?\s*no|"
    r"prescription\s+authori[sz]ed|signature|"
    r"(?:mobile|phone|tel|email|website|www\.)|"
    r"consultant|m\.?b\.?b\.?s|m\.?d\b|m\.?s\b|d\.?n\.?b|"
    r"date\s*[:.]|time\s*[:.]|uhid|patient\s+name|age\s*/?\s*sex|"
    r"[-_=]{3,})",
    re.IGNORECASE,
)


@dataclass
class MedicineRead:
    """One medicine line, and how sure we are of the name on it."""

    raw_line: str
    name: str                       # the formulary name — never the OCR token
    read_as: Optional[str] = None   # the OCR token, when it differed
    ingredients: List[str] = field(default_factory=list)
    strength: Optional[str] = None
    dose_notation: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    timing: Optional[str] = None
    exact: bool = True              # False when matched through a misreading

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_line": self.raw_line,
            "name": self.name,
            "read_as": self.read_as,
            "ingredients": self.ingredients,
            "strength": self.strength,
            "dose_notation": self.dose_notation,
            "frequency": self.frequency,
            "duration": self.duration,
            "timing": self.timing,
            "exact": self.exact,
        }


@dataclass
class PrescriptionReading:
    #: Named exactly as the formulary names them. Safe to state as fact.
    medicines: List[MedicineRead] = field(default_factory=list)
    #: Close but not certain. The printed line leads; the name is a question.
    possible_medicines: List[MedicineRead] = field(default_factory=list)
    #: Dosing lines that matched nothing. Shown verbatim.
    unidentified_lines: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)

    @property
    def confident(self) -> bool:
        """Is there anything here that can be stated as fact?

        One exactly matched medicine or one stated problem is enough to be
        worth showing. Nothing at all means the page was not read, and saying
        so is the only honest option left.
        """
        return bool(self.medicines or self.problems)

    @property
    def needs_manual_check(self) -> bool:
        """Was anything left over that a person needs to look at?"""
        return bool(self.possible_medicines or self.unidentified_lines)

    def to_dict(self) -> Dict[str, object]:
        return {
            "medicines": [item.to_dict() for item in self.medicines],
            "possible_medicines": [item.to_dict() for item in self.possible_medicines],
            "unidentified_lines": self.unidentified_lines,
            "problems": self.problems,
            "needs_manual_check": self.needs_manual_check,
        }


def _formulary_index() -> Dict[str, str]:
    """Every name a medicine can legitimately be written under.

    Three sources, all matched exactly: the formulary's own brand names, the
    single active ingredient where there is only one, and the brand table
    behind the prescribing copilot — which is where "Pan" resolves to
    pantoprazole, something patients write that no formulary name matches.
    """
    index: Dict[str, str] = {}
    for item in formulary.FORMULARY:
        key = normalize_name(item.name)
        if key:
            index.setdefault(key, item.name)
        if len(item.ingredients) == 1:
            index.setdefault(normalize_name(item.ingredients[0]), item.name)
    for brand, ingredients in BRAND_INGREDIENTS.items():
        key = normalize_name(brand)
        if not key or key in index:
            continue
        matched = next(
            (
                item.name for item in formulary.FORMULARY
                if set(item.ingredients) == set(ingredients)
            ),
            None,
        )
        index[key] = matched or " + ".join(part.title() for part in ingredients)
    return index


_INDEX: Dict[str, str] = _formulary_index()
_ALL_KEYS: List[str] = sorted(_INDEX)


def _ingredients_for(name: str) -> List[str]:
    for item in formulary.FORMULARY:
        if item.name == name:
            return list(item.ingredients)
    return []


def _lookup(token: str) -> Tuple[Optional[str], bool]:
    """Resolve one token to a medicine name. Returns (name, was_exact)."""
    key = normalize_name(token)
    if not key:
        return None, True
    exact = _INDEX.get(key)
    if exact is not None:
        return exact, True
    if len(key) < 5:
        # Short tokens fuzzy-match far too eagerly — "min" sits one edit from
        # several drug names and "PAN" from "PANTOP". Short names match
        # exactly or not at all.
        return None, True

    close = difflib.get_close_matches(key, _ALL_KEYS, n=2, cutoff=_FUZZY_CUTOFF)
    if not close:
        return None, True
    # A near match is only worth offering when it is the clear near match.
    # Two candidates equally close means we cannot tell which drug this is,
    # and choosing one would be guessing at somebody's prescription.
    if len(close) == 2 and _INDEX[close[0]] != _INDEX[close[1]]:
        best = difflib.SequenceMatcher(None, key, close[0]).ratio()
        second = difflib.SequenceMatcher(None, key, close[1]).ratio()
        if best - second < 0.05:
            return None, True
    return _INDEX[close[0]], False


def _match_line(line: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Find the drug on one line. Returns (name, token as read, exact).

    Only the start of the line is considered. A drug name is the first thing
    written on a prescription line, and scanning the whole line lets the
    dosing text fuzzy-match a name — attaching an invented medicine to a line
    that never named one.
    """
    stripped = _LEADING_NOISE.sub("", line)
    words = [word for word in re.split(r"[\s,;/()]+", stripped) if word]

    # Two words first: several formulary entries are two words ("Zerodol SP",
    # "Meftal Spas"), and matching only the first resolves to a different
    # medicine with different ingredients.
    for size in (2, 1):
        chunk = " ".join(words[:size])
        if not chunk or not re.search(r"[A-Za-z]{3,}", chunk):
            continue
        name, exact = _lookup(chunk)
        if name is not None:
            return name, chunk, exact
    return None, None, True


def _clean_problem(text: str) -> str:
    return " ".join(text.split()).strip(" .,;:-")


def _informative(entry: MedicineRead) -> tuple:
    """Which dosing details this entry actually carries."""
    return tuple(
        value is not None
        for value in (
            entry.strength, entry.dose_notation, entry.frequency,
            entry.duration, entry.timing,
        )
    )


def _merge_duplicates(entries: List[MedicineRead]) -> List[MedicineRead]:
    """Drop entries that add nothing over another entry for the same drug.

    "Paracetamol" with no dosing beside "Paracetamol 600 mg" is the same fact
    told twice, once less usefully. But two different strengths of the same
    drug are two different instructions and both are kept.
    """
    kept: List[MedicineRead] = []
    for entry in entries:
        detail = _informative(entry)
        redundant = False
        for index, existing in enumerate(kept):
            if existing.name != entry.name:
                continue
            other = _informative(existing)
            # Same drug, and everything this entry knows the other knows too.
            if all(mine <= theirs for mine, theirs in zip(detail, other)):
                redundant = True
                break
            if all(theirs <= mine for mine, theirs in zip(detail, other)):
                kept[index] = entry
                redundant = True
                break
        if not redundant:
            kept.append(entry)
    return kept


def read_prescription(text: str) -> PrescriptionReading:
    """Pull medicines and stated problems off a prescription. Nothing else."""
    reading = PrescriptionReading()
    seen_medicines: set = set()

    for raw_line in (text or "").splitlines():
        line = " ".join(raw_line.replace(" ", " ").split())
        if len(line) < 3 or _FURNITURE.match(line):
            continue

        # --- a stated problem -------------------------------------------
        heading = _PROBLEM_HEADING.match(line)
        if heading:
            rest = _clean_problem(heading.group("rest"))
            # Carried verbatim. Whatever the doctor wrote is the diagnosis;
            # rewording it here would be inventing a clinical opinion.
            if rest and len(rest) > 2:
                if rest not in reading.problems:
                    reading.problems.append(rest)
            continue

        name, token, exact = _match_line(line)
        looks_prescribed = bool(
            _DOSE_NOTATION.search(line) or _FREQUENCY.search(line) or _STRENGTH.search(line)
        )

        if name is None:
            # Only lines that were plainly meant to be a drug are worth
            # showing as unread — a stray letterhead fragment is not.
            if looks_prescribed and line not in reading.unidentified_lines:
                reading.unidentified_lines.append(line)
            continue

        strength_match = _STRENGTH.search(line)
        duration_match = _DURATION.search(line)
        dose_match = _DOSE_NOTATION.search(line)
        frequency_match = _FREQUENCY.search(line)
        timing_match = _TIMING.search(line)

        entry = MedicineRead(
            raw_line=line,
            name=name,
            read_as=(
                None if normalize_name(token or "") == normalize_name(name)
                else _TOKEN_TAIL.sub("", token or "").strip()
            ),
            ingredients=_ingredients_for(name),
            strength=(
                f"{strength_match.group(1)} {strength_match.group(2).lower()}"
                if strength_match else None
            ),
            dose_notation=dose_match.group(0).replace(" ", "") if dose_match else None,
            frequency=frequency_match.group(1).upper() if frequency_match else None,
            duration=(
                f"{duration_match.group(1)} {duration_match.group(2).lower()}"
                if duration_match else None
            ),
            timing=timing_match.group(1).lower() if timing_match else None,
            exact=exact,
        )

        # The same drug printed twice on one sheet is one medicine.
        signature = (entry.name, entry.strength, entry.dose_notation, entry.frequency)
        if signature in seen_medicines:
            continue
        seen_medicines.add(signature)

        # An exact name is a fact about the prescription. A near match is a
        # question about it, and the two must not share a heading.
        if exact:
            reading.medicines.append(entry)
        else:
            reading.possible_medicines.append(entry)

    reading.medicines = _merge_duplicates(reading.medicines)
    reading.possible_medicines = _merge_duplicates(reading.possible_medicines)
    return reading
