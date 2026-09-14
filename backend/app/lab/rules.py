"""Laboratory rules: reading a typed result, choosing its range, flagging it,
and deciding what may be verified.

Pure functions, no database, so every rule here is tested directly.

The same discipline as reading an outside report applies, and more strictly,
because this report goes out under the hospital's own name:

* **A flag is arithmetic against a range the pathologist has set.** Nothing
  is inferred. A value with no applicable range is printed without a flag,
  and the screen says why, rather than being compared against a guess.
* **A value that is not clearly a number is refused, not interpreted.**
  "12,5" could be twelve and a half or a typing slip; the technician is asked
  to type it again. Indian digit grouping ("1,50,000") is accepted because it
  is unambiguous.
* **A limit is only flagged when the limit alone settles it.** "<0.5" against
  a range of 0 - 1 could be anywhere in the range; it is shown as not compared.
* **Sex is never assumed.** A patient recorded as neither male nor female is
  matched only against ranges that apply to everyone.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

RESULT_TYPES = ("numeric", "text", "choice", "heading")
MASTER_KINDS = ("unit", "method", "specimen", "antibiotic", "organism", "group")
SUSCEPTIBILITY = {"S": "Sensitive", "I": "Intermediate", "R": "Resistant"}
BILLING_MODES = ("invoice", "ipd", "unbilled")
PRIORITIES = ("routine", "urgent", "stat")

FLAG_LABEL = {
    "normal": "",
    "low": "L",
    "high": "H",
    "critical_low": "LL",
    "critical_high": "HH",
    "abnormal": "*",
}
CRITICAL_FLAGS = {"critical_low", "critical_high"}
ABNORMAL_FLAGS = {"low", "high", "critical_low", "critical_high", "abnormal"}

MAX_TEXT_RESULT = 500
MAX_ISOLATES = 3

_OPERATOR = re.compile(r"^(<=|>=|<|>)\s*(.*)$")
_PLAIN = re.compile(r"^-?\d+(?:\.\d+)?$")
# 1,50,000 (Indian) or 150,000 / 1,500,000 (international). "12,34" is not
# accepted: it could be a decimal comma.
_GROUPED = re.compile(r"^\d{1,3}(?:(?:,\d{2})*,\d{3}|(?:,\d{3})+)(?:\.\d+)?$")


# ------------------------------------------------------------------ numbers
@dataclass(frozen=True)
class Reading:
    operator: Optional[str]
    number: float


def read_number(text: Optional[str]) -> Optional[Reading]:
    """A typed numeric result, or None when it is not unambiguously a number."""
    raw = (text or "").strip()
    if not raw:
        return None
    operator = None
    match = _OPERATOR.match(raw)
    if match:
        operator, raw = match.group(1), match.group(2).strip()
    if _GROUPED.match(raw):
        raw = raw.replace(",", "")
    if not _PLAIN.match(raw):
        return None
    if operator and raw.startswith("-"):
        return None
    return Reading(operator, float(raw))


def fmt(number: Optional[float]) -> str:
    """12.0 -> "12", 0.25 -> "0.25": a range printed the way a person writes it."""
    if number is None:
        return ""
    return f"{number:g}" if abs(number) < 1e7 else f"{number:.0f}"


# ------------------------------------------------------------------- ranges
def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_range(entry: Dict[str, Any]) -> Dict[str, Any]:
    sex = (entry.get("sex") or None)
    return {
        "sex": sex if sex in ("male", "female") else None,
        "min_age": int(entry.get("min_age") or 0),
        "max_age": int(entry.get("max_age") if entry.get("max_age") not in (None, "") else 120),
        "low": _num(entry.get("low")),
        "high": _num(entry.get("high")),
        "critical_low": _num(entry.get("critical_low")),
        "critical_high": _num(entry.get("critical_high")),
    }


def _describe(entry: Dict[str, Any]) -> str:
    who = {"male": "Males", "female": "Females"}.get(entry["sex"], "Everyone")
    if entry["min_age"] > 0 or entry["max_age"] < 120:
        who += f" aged {entry['min_age']}-{entry['max_age']}"
    return who


def validate_ranges(ranges: Iterable[Dict[str, Any]]) -> List[str]:
    """Problems with a parameter's ranges, in words a pathologist can act on."""
    problems: List[str] = []
    cleaned = [clean_range(entry) for entry in ranges]
    for entry in cleaned:
        who = _describe(entry)
        low, high = entry["low"], entry["high"]
        if low is None and high is None:
            problems.append(f"{who}: give a lower or an upper limit")
            continue
        if entry["min_age"] < 0 or entry["max_age"] > 120 or entry["min_age"] > entry["max_age"]:
            problems.append(f"{who}: the age band is not valid")
        if low is not None and high is not None and low > high:
            problems.append(f"{who}: the lower limit is above the upper limit")
        if entry["critical_low"] is not None and low is not None and entry["critical_low"] > low:
            problems.append(f"{who}: the critical low is above the lower limit")
        if entry["critical_high"] is not None and high is not None and entry["critical_high"] < high:
            problems.append(f"{who}: the critical high is below the upper limit")
    for index, first in enumerate(cleaned):
        for second in cleaned[index + 1:]:
            if first["sex"] != second["sex"]:
                continue
            if first["min_age"] <= second["max_age"] and second["min_age"] <= first["max_age"]:
                problems.append(
                    f"{_describe(first)} and {_describe(second)} overlap: "
                    "a patient would match two ranges"
                )
    return problems


def select_range(
    ranges: Iterable[Dict[str, Any]], *, sex: Optional[str], age: Optional[int]
) -> Optional[Dict[str, Any]]:
    """The one range that applies to this patient, or None.

    A sex-specific range beats a general one. A patient whose sex is not male
    or female matches only general ranges, and a patient of unknown age
    matches only ranges covering every age.
    """
    best = None
    best_score = -1
    for raw in ranges:
        entry = clean_range(raw)
        if entry["low"] is None and entry["high"] is None:
            continue
        if entry["sex"] is not None and entry["sex"] != sex:
            continue
        whole_life = entry["min_age"] <= 0 and entry["max_age"] >= 120
        if age is None:
            if not whole_life:
                continue
        elif not (entry["min_age"] <= age <= entry["max_age"]):
            continue
        score = (2 if entry["sex"] is not None else 0) + (0 if whole_life else 1)
        if score > best_score:
            best, best_score = entry, score
    return best


def range_text(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    if entry is None:
        return None
    low, high = entry["low"], entry["high"]
    if low is not None and high is not None:
        return f"{fmt(low)} - {fmt(high)}"
    if high is not None:
        return f"Up to {fmt(high)}"
    if low is not None:
        return f"Above {fmt(low)}"
    return None


# --------------------------------------------------------------- evaluation
def evaluate(
    parameter: Dict[str, Any], value: Optional[str], *, sex: Optional[str], age: Optional[int]
) -> Dict[str, Any]:
    """Judge one typed result against its parameter.

    Returns flag (None when not compared), the reference text to print, a note
    for the screen, and an error when the value cannot be accepted at all.
    """
    kind = parameter.get("result_type") or "numeric"
    text = (value or "").strip()
    out: Dict[str, Any] = {"flag": None, "reference_text": parameter.get("range_text") or None,
                           "note": None, "error": None}
    if kind == "heading" or not text:
        return out

    if kind == "text":
        if len(text) > MAX_TEXT_RESULT:
            out["error"] = f"{parameter.get('name')}: keep the result under {MAX_TEXT_RESULT} characters"
        return out

    if kind == "choice":
        choices = [str(choice) for choice in parameter.get("choices") or []]
        chosen = next((choice for choice in choices if choice.lower() == text.lower()), None)
        if chosen is None:
            out["error"] = f"{parameter.get('name')}: choose one of {', '.join(choices)}"
            return out
        normal = [str(entry).lower() for entry in parameter.get("normal_values") or []]
        if normal:
            out["flag"] = "normal" if chosen.lower() in normal else "abnormal"
            if not out["reference_text"]:
                out["reference_text"] = " / ".join(str(entry) for entry in parameter.get("normal_values"))
        return out

    reading = read_number(text)
    if reading is None:
        out["error"] = (f"{parameter.get('name')}: \"{text}\" is not a number. "
                        "Type digits with a decimal point, for example 12.5")
        return out

    ranges = parameter.get("ranges") or []
    entry = select_range(ranges, sex=sex, age=age)
    if not out["reference_text"]:
        out["reference_text"] = range_text(entry)
    if entry is None:
        out["note"] = ("No reference range applies to this patient; not compared" if ranges
                       else "No reference range set; not compared")
        return out

    low, high = entry["low"], entry["high"]
    number = reading.number
    if reading.operator is None:
        if entry["critical_low"] is not None and number <= entry["critical_low"]:
            out["flag"] = "critical_low"
        elif entry["critical_high"] is not None and number >= entry["critical_high"]:
            out["flag"] = "critical_high"
        elif low is not None and number < low:
            out["flag"] = "low"
        elif high is not None and number > high:
            out["flag"] = "high"
        else:
            out["flag"] = "normal"
        return out

    # A reported limit: flagged only when the limit settles it on its own.
    if reading.operator in ("<", "<="):
        if low is not None and (number < low or (reading.operator == "<" and number <= low)):
            out["flag"] = "low"
        elif high is not None and number <= high and (low is None or low <= 0):
            out["flag"] = "normal"
    else:
        if high is not None and (number > high or (reading.operator == ">" and number >= high)):
            out["flag"] = "high"
        elif low is not None and number >= low and high is None:
            out["flag"] = "normal"
    if out["flag"] is None:
        out["note"] = "Reported as a limit that falls inside the range; not compared"
    return out


def evaluate_all(
    parameters: List[Dict[str, Any]],
    values: Dict[str, Optional[str]],
    prints: Dict[str, bool],
    *,
    sex: Optional[str],
    age: Optional[int],
) -> tuple:
    """The result rows to store for one test, and every error found."""
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for parameter in parameters:
        key = str(parameter["id"])
        typed = values.get(key)
        typed = typed.strip() if isinstance(typed, str) else None
        judged = evaluate(parameter, typed, sex=sex, age=age)
        if judged["error"]:
            errors.append(judged["error"])
        rows.append({
            "parameter_id": key,
            "name": parameter.get("name"),
            "result_type": parameter.get("result_type") or "numeric",
            "unit": parameter.get("unit") or None,
            "method": parameter.get("method") or None,
            "value": typed or None,
            "flag": judged["flag"],
            "reference_text": judged["reference_text"],
            "note": judged["note"],
            "print": bool(prints.get(key, parameter.get("print_default", True))),
        })
    return rows, errors


def critical_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("flag") in CRITICAL_FLAGS]


# ------------------------------------------------------------------ culture
def clean_culture(culture: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    culture = culture or {}
    isolates = []
    for isolate in culture.get("isolates") or []:
        panel = []
        for row in isolate.get("antibiotics") or []:
            name = (row.get("name") or "").strip()
            result = (row.get("result") or "").strip().upper()
            if not name and not result:
                continue
            panel.append({"name": name, "result": result,
                          "value": (row.get("value") or "").strip() or None})
        isolates.append({
            "organism": (isolate.get("organism") or "").strip(),
            "colony_count": (isolate.get("colony_count") or "").strip() or None,
            "antibiotics": panel,
        })
    growth = culture.get("growth")
    return {
        "specimen": (culture.get("specimen") or "").strip() or None,
        "growth": growth if growth in ("growth", "no_growth") else None,
        "incubation": (culture.get("incubation") or "").strip() or None,
        "isolates": isolates,
        "comment": (culture.get("comment") or "").strip() or None,
    }


def check_culture(culture: Optional[Dict[str, Any]]) -> List[str]:
    data = clean_culture(culture)
    problems: List[str] = []
    if not data["specimen"]:
        problems.append("Record the specimen cultured")
    if data["growth"] is None:
        problems.append("Record whether there was growth")
        return problems
    if data["growth"] == "no_growth":
        if data["isolates"]:
            problems.append("Remove the organisms: the culture is recorded as no growth")
        return problems
    if not data["isolates"]:
        problems.append("Name the organism isolated")
    if len(data["isolates"]) > MAX_ISOLATES:
        problems.append(f"Report at most {MAX_ISOLATES} organisms")
    for number, isolate in enumerate(data["isolates"], start=1):
        label = isolate["organism"] or f"Organism {number}"
        if not isolate["organism"]:
            problems.append(f"Organism {number}: name the organism")
        if not isolate["antibiotics"]:
            problems.append(f"{label}: record the antibiotic sensitivity")
        seen = set()
        for row in isolate["antibiotics"]:
            if not row["name"]:
                problems.append(f"{label}: an antibiotic row has no name")
            elif row["name"].lower() in seen:
                problems.append(f"{label}: {row['name']} is listed twice")
            seen.add(row["name"].lower())
            if row["result"] not in SUSCEPTIBILITY:
                problems.append(f"{label}: mark {row['name'] or 'each antibiotic'} S, I or R")
    return problems


# ------------------------------------------------------------- verification
def check_for_verify(
    *, is_culture: bool, rows: List[Dict[str, Any]], culture: Optional[Dict[str, Any]],
    errors: List[str],
) -> List[str]:
    """What stops a test being verified. Empty means it may be signed."""
    problems = list(errors)
    if is_culture:
        return problems + check_culture(culture)
    printable = [row for row in rows if row["result_type"] != "heading" and row["print"]]
    if not printable:
        problems.append("Nothing is ticked to print")
    for row in printable:
        if not row["value"]:
            problems.append(f"Enter {row['name']}, or untick it from printing")
    return problems


def request_status(item_states: Iterable[str]) -> str:
    """One request's status from its tests'."""
    states = [state for state in item_states]
    live = [state for state in states if state != "cancelled"]
    if not live:
        return "cancelled"
    if all(state == "verified" for state in live):
        return "verified"
    if any(state == "verified" for state in live):
        return "partly_verified"
    if any(state == "entered" for state in live):
        return "in_progress"
    if any(state == "collected" for state in live):
        return "collected"
    return "registered"


# ------------------------------------------------------------ the printout
def match_printout(
    parameters: List[Dict[str, Any]], parsed: Iterable[Any], *, normalize_unit, clean_name
) -> Dict[str, Any]:
    """Suggest values for a test from an analyser printout.

    Suggestions only: nothing is saved until the technician confirms each one.
    A parameter matched by two lines is not suggested at all, and a value in a
    different unit from the parameter is not suggested — it is listed so the
    technician can see why.
    """
    by_key: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for parameter in parameters:
        if (parameter.get("result_type") or "numeric") == "heading":
            continue
        if parameter.get("analyte_key"):
            by_key[parameter["analyte_key"]] = parameter
        for name in [parameter.get("name") or "", *(parameter.get("aliases") or [])]:
            if clean_name(name):
                by_name[clean_name(name)] = parameter

    found: Dict[str, List[Dict[str, Any]]] = {}
    unmatched: List[str] = []
    mismatched: List[str] = []
    for line in parsed:
        parameter = None
        if getattr(line, "analyte_key", None):
            parameter = by_key.get(line.analyte_key)
        if parameter is None:
            parameter = by_name.get(clean_name(line.printed_name or ""))
        if parameter is None:
            if line.raw_line:
                unmatched.append(line.raw_line)
            continue
        if line.value_numeric is not None:
            value = f"{line.operator or ''}{fmt(line.value_numeric)}"
        else:
            value = (line.value_text or "").strip()
        if not value:
            unmatched.append(line.raw_line)
            continue
        printed_unit = normalize_unit(line.unit)
        expected_unit = normalize_unit(parameter.get("unit"))
        if printed_unit and expected_unit and printed_unit != expected_unit:
            mismatched.append(f"{line.raw_line} (printed in {line.unit}; this test records {parameter.get('unit')})")
            continue
        found.setdefault(str(parameter["id"]), []).append({"value": value, "raw_line": line.raw_line})

    suggestions = []
    conflicts = []
    for parameter_id, hits in found.items():
        name = next(p.get("name") for p in parameters if str(p["id"]) == parameter_id)
        if len(hits) > 1:
            conflicts.append(f"{name} appears {len(hits)} times on the printout; enter it by hand")
            continue
        suggestions.append({"parameter_id": parameter_id, "name": name, **hits[0]})
    return {
        "suggestions": suggestions,
        "conflicts": conflicts,
        "unit_mismatches": mismatched,
        "unmatched_lines": unmatched[:40],
        "unmatched_count": len(unmatched),
    }
