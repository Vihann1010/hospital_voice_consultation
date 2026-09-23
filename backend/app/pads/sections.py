"""What a pad section is, what may be stored in one, and how it is filled.

A layout is a list of sections and a document is a dict of values keyed by
section. Both arrive from a browser, so both are validated here rather than
trusted: a layout is configuration that decides what prints on a legal
document, and a value is clinical content that will be signed.

Four kinds of section, and the value each one holds:

  text    {"text": "..."}              free prose, with template variables
  fields  {"fields": {key: value}}     typed inputs — numbers, dates, choices
  list    {"items": ["...", "..."]}    one phrase per line, from the catalogue
  ai      {"items": [...]} or {"text"} drafted from the intake, then edited

Nothing in this module touches the database. Every function takes plain data
and returns plain data, so the rules can be tested without a session.
"""
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

SectionKind = Literal["text", "fields", "list", "ai", "medicines", "investigations"]
FieldType = Literal["text", "textarea", "number", "date", "select", "multiselect", "checkbox"]

# Where an AI section's first draft comes from. Each maps onto a part of the
# intake dossier the voice pipeline already produces; nothing new is generated
# for the pad.
AISource = Literal[
    "intake_summary",
    #: The same history in Hindi, for the copy the patient takes home.
    "intake_summary_hi",
    #: Allergies, medicines already being taken, past illness and surgery.
    "background",
    "red_flags",
    "differentials",
    "suggested_investigations",
]

# Facts already recorded on the admission, copied into a new inpatient
# document so nobody retypes the diagnosis the admitting doctor wrote an hour
# earlier. Copied once, when the draft is made, and then the doctor's to edit.
PrefillSource = Literal[
    "reason_for_admission", "provisional_diagnosis", "final_diagnosis", "allergies",
    # From a theatre booking: the operation with its side, the diagnosis it was
    # booked for, and the team.
    "procedure", "diagnosis", "team",
]

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")

# Generous, but finite. A section value is printed, and a paste of an entire
# referral letter into a single field is better refused than rendered across
# nine pages of a one-page OPD slip.
MAX_TEXT = 8000
MAX_ITEM = 400
MAX_ITEMS = 60

# A prescribed line, in the shape the prescription table stores it, so a pad
# that is signed can issue the prescription without reshaping anything. The
# lengths are the column lengths: a value that would be truncated on the way
# to the database is better trimmed here, where the doctor can still see it.
MEDICINE_FIELDS: Dict[str, int] = {
    "formulary_code": 64,
    "name": 255,
    "generic": 255,
    "form": 64,
    "strength": 64,
    "dosage": 120,
    "frequency_code": 32,
    "frequency_text": 120,
    "duration": 120,
    "timing": 120,
    "route": 64,
    "instructions": MAX_TEXT,
}

# How a line arrived: read off the doctor's dictation, chosen from the
# formulary, or typed. Kept because it is the only way to measure whether
# dictation is working, and because a dictated line the doctor never touched
# reads differently in an audit from one they typed themselves.
MEDICINE_SOURCES = ("dictated", "catalog", "manual")

#: An investigation the doctor has advised, which becomes a real order when
#: the pad is signed.
INVESTIGATION_FIELDS: Dict[str, int] = {
    "code": 32,
    "name": 255,
    "note": MAX_ITEM,
}


class FieldSpec(BaseModel):
    """One typed input inside a `fields` section."""

    key: str
    label: str = Field(min_length=1, max_length=80)
    type: FieldType = "text"
    unit: Optional[str] = Field(default=None, max_length=24)
    options: List[str] = Field(default_factory=list)
    required: bool = False
    catalogue_category: Optional[str] = None

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not _KEY_RE.match(value):
            raise ValueError(
                f"Field key {value!r} must be lower-case letters, digits and underscores."
            )
        return value

    @model_validator(mode="after")
    def _choices_need_options(self) -> "FieldSpec":
        if self.type in ("select", "multiselect") and not self.options:
            raise ValueError(f"Field {self.key!r} is a choice but lists no options.")
        return self


class SectionSpec(BaseModel):
    """One section of a layout."""

    key: str
    title: str = Field(min_length=1, max_length=80)
    kind: SectionKind
    # Three separate switches, because they answer three separate questions.
    # A section can be worth seeing on screen and wrong on the patient's copy
    # (differentials), or worth carrying to next visit and not worth printing.
    visible_in_pad: bool = True
    visible_in_print: bool = True
    carry_forward: bool = False
    catalogue_category: Optional[str] = None
    placeholder: Optional[str] = Field(default=None, max_length=160)
    fields: List[FieldSpec] = Field(default_factory=list)
    ai_source: Optional[AISource] = None
    prefill_from: Optional[PrefillSource] = None

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not _KEY_RE.match(value):
            raise ValueError(
                f"Section key {value!r} must be lower-case letters, digits and underscores."
            )
        return value

    @model_validator(mode="after")
    def _kind_rules(self) -> "SectionSpec":
        if self.kind == "fields":
            if not self.fields:
                raise ValueError(f"Section {self.key!r} holds typed fields but defines none.")
            keys = [spec.key for spec in self.fields]
            if len(keys) != len(set(keys)):
                raise ValueError(f"Section {self.key!r} defines the same field twice.")
        if self.kind == "ai" and not self.ai_source:
            raise ValueError(f"AI section {self.key!r} does not say what it is drafted from.")
        # An investigations section may also carry suggestions from the
        # intake, which is how the doctor gets to add them with one tap.
        if self.kind not in ("ai", "investigations") and self.ai_source:
            raise ValueError(f"Only an AI section can be drafted from the intake ({self.key!r}).")
        if self.kind == "investigations" and self.ai_source != "suggested_investigations":
            if self.ai_source is not None:
                raise ValueError(
                    f"Section {self.key!r} lists investigations, so it can only be "
                    "drafted from the suggested investigations."
                )
        if self.kind in ("medicines", "investigations") and self.fields:
            raise ValueError(
                f"Section {self.key!r} holds its own kind of row and defines no fields."
            )
        if self.kind == "medicines" and self.catalogue_category:
            raise ValueError(
                f"Section {self.key!r} prescribes from the formulary, not from a "
                "phrase catalogue."
            )
        if self.prefill_from and self.kind not in ("text", "list"):
            raise ValueError(
                f"Section {self.key!r} can only be filled from the admission if it holds "
                "text or a list."
            )
        return self


class LayoutError(ValueError):
    """A layout that cannot be saved, with a reason a person can act on."""


def _explain(exc: ValidationError, index: int, raw: Any) -> str:
    """Turn a validation failure into a sentence naming the section at fault.

    Pydantic's own first line is "1 validation error for SectionSpec", which
    tells an administrator that something is wrong and nothing about what.
    """
    first = exc.errors()[0]
    message = str(first.get("msg", "is not valid")).removeprefix("Value error, ")
    title = raw.get("title") if isinstance(raw, dict) else None
    where = f"Section {index + 1}" + (f" ({title})" if title else "")
    if first.get("type") == "value_error":
        # Our own validators already name the key or field in the message.
        return f"{where}: {message}"
    location = ".".join(str(part) for part in first.get("loc", ()))
    return f"{where}, {location}: {message}" if location else f"{where}: {message}"


def validate_layout(sections: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse and normalise a layout. Raises LayoutError with the first problem."""
    parsed: List[SectionSpec] = []
    for index, raw in enumerate(sections):
        try:
            parsed.append(SectionSpec.model_validate(raw))
        except ValidationError as exc:
            raise LayoutError(_explain(exc, index, raw)) from exc

    if not parsed:
        raise LayoutError("A layout needs at least one section.")
    keys = [section.key for section in parsed]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise LayoutError(f"Two sections share the key {duplicates[0]!r}.")
    return [section.model_dump() for section in parsed]


# --------------------------------------------------------------------- values
def _clean_text(value: Any, limit: int = MAX_TEXT) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "").strip()[:limit]


def _clean_items(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for entry in value:
        text = _clean_text(entry, MAX_ITEM)
        if text and text not in items:
            items.append(text)
    return items[:MAX_ITEMS]


def _clean_field(spec: Dict[str, Any], value: Any) -> Any:
    kind = spec.get("type", "text")
    if value is None or value == "":
        return None if kind != "multiselect" else []
    if kind == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else round(number, 3)
    if kind == "date":
        try:
            return date.fromisoformat(str(value)[:10]).isoformat()
        except ValueError:
            return None
    if kind == "checkbox":
        return bool(value)
    if kind == "select":
        return value if value in spec.get("options", []) else None
    if kind == "multiselect":
        options = spec.get("options", [])
        return [item for item in (value if isinstance(value, list) else []) if item in options]
    return _clean_text(value, MAX_TEXT if kind == "textarea" else MAX_ITEM)


def _clean_rows(
    value: Any, spec: Dict[str, int], *, required: str, extra: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Clean a list of row-shaped entries, dropping any without their one
    indispensable field.

    A medicine with no name is not a medicine, and carrying it forward as a
    blank row onto a printed prescription is worse than losing it.
    """
    rows: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for entry in value:
        if not isinstance(entry, dict):
            continue
        row: Dict[str, Any] = {}
        for key, limit in spec.items():
            text = _clean_text(entry.get(key), limit)
            if text:
                row[key] = text
        if not row.get(required):
            continue
        for key, allowed in (extra or {}).items():
            given = entry.get(key)
            row[key] = given if given in allowed else allowed[-1]
        rows.append(row)
        if len(rows) >= MAX_ITEMS:
            break
    return rows


def clean_medicines(value: Any) -> List[Dict[str, Any]]:
    return _clean_rows(
        value, MEDICINE_FIELDS, required="name", extra={"source": MEDICINE_SOURCES}
    )


def clean_investigations(value: Any) -> List[Dict[str, Any]]:
    return _clean_rows(value, INVESTIGATION_FIELDS, required="name")


def clean_values(sections: List[Dict[str, Any]], values: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only what the layout allows, in the shape it expects.

    Unknown section keys are dropped rather than refused: a draft saved a
    moment before an administrator removed a section should still save.
    """
    cleaned: Dict[str, Any] = {}
    incoming = values or {}
    for section in sections:
        key = section["key"]
        if key not in incoming:
            continue
        raw = incoming[key] if isinstance(incoming[key], dict) else {}
        kind = section["kind"]

        if kind == "text":
            cleaned[key] = {"text": _clean_text(raw.get("text"))}
        elif kind == "list":
            cleaned[key] = {"items": _clean_items(raw.get("items"))}
        elif kind == "fields":
            given = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
            cleaned[key] = {
                "fields": {
                    spec["key"]: _clean_field(spec, given.get(spec["key"]))
                    for spec in section.get("fields", [])
                }
            }
        elif kind == "ai":
            entry: Dict[str, Any] = {}
            if "text" in raw:
                entry["text"] = _clean_text(raw.get("text"))
            if "items" in raw:
                entry["items"] = _clean_items(raw.get("items"))
            # What the model offered and the doctor has not taken. Held apart
            # so an unread suggestion is never mistaken for the doctor's own
            # words, and never printed.
            if "suggestions" in raw:
                entry["suggestions"] = _clean_items(raw.get("suggestions"))
            cleaned[key] = entry
        elif kind == "medicines":
            # Suggestions are held apart from the prescription itself. Nothing
            # is prescribed until the doctor taps it across, so a line the
            # dictation heard but the doctor never accepted can never reach
            # the printed slip.
            cleaned[key] = {
                "medicines": clean_medicines(raw.get("medicines")),
                "suggestions": clean_medicines(raw.get("suggestions")),
            }
        elif kind == "investigations":
            cleaned[key] = {
                "investigations": clean_investigations(raw.get("investigations")),
                "suggestions": clean_investigations(raw.get("suggestions")),
            }
    return cleaned


def is_empty(section: Dict[str, Any], value: Optional[Dict[str, Any]]) -> bool:
    """Would this section print nothing?

    Suggestions do not count. A pad showing three medicines the doctor has not
    accepted has an empty prescription, and printing it as though it were the
    doctor's would put words in their mouth.
    """
    if not value:
        return True
    if value.get("text"):
        return False
    if value.get("items"):
        return False
    if value.get("medicines") or value.get("investigations"):
        return False
    fields = value.get("fields") or {}
    return all(item in (None, "", [], False) for item in fields.values())


# ----------------------------------------------------------------- variables
# The old system's word-pad variables, carried over under the same meaning so
# the hospital's existing templates read correctly once retyped.
TEMPLATE_VARIABLES: Dict[str, str] = {
    "patient_name": "Patient's name",
    "uhid": "UHID",
    "age": "Age in years",
    "sex": "Sex",
    "address": "Address",
    "guardian": "Guardian, with relation",
    "date": "Today's date",
}

_VARIABLE_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def variable_context(patient: Any, on: Optional[date] = None) -> Dict[str, str]:
    """The values a template's {{variables}} resolve to for one patient."""
    guardian = ""
    if getattr(patient, "guardian_name", None):
        relation = getattr(patient, "guardian_relation", None) or ""
        guardian = f"{relation} {patient.guardian_name}".strip()
    address = ", ".join(
        part for part in (
            getattr(patient, "address", None),
            getattr(patient, "city", None),
        ) if part
    )
    gender = getattr(patient, "gender", None)
    return {
        "patient_name": getattr(patient, "name", "") or "",
        "uhid": getattr(patient, "uhid", "") or "",
        "age": str(getattr(patient, "age", "") or ""),
        "sex": (getattr(gender, "value", gender) or "").title(),
        "address": address,
        "guardian": guardian,
        "date": (on or date.today()).strftime("%d %b %Y"),
    }


def render_variables(text: str, context: Dict[str, str]) -> str:
    """Substitute known variables; leave unknown ones visible.

    An unknown variable is left as written rather than blanked, so a typo in
    a template shows up on screen as "{{patinet_name}}" instead of silently
    printing a certificate with the patient's name missing.
    """
    def swap(match: "re.Match[str]") -> str:
        name = match.group(1)
        return context[name] if name in context else match.group(0)

    return _VARIABLE_RE.sub(swap, text or "")


def apply_variables(values: Dict[str, Any], context: Dict[str, str]) -> Dict[str, Any]:
    """Resolve variables throughout a set of values."""
    resolved: Dict[str, Any] = {}
    for key, value in (values or {}).items():
        if not isinstance(value, dict):
            continue
        entry = dict(value)
        if isinstance(entry.get("text"), str):
            entry["text"] = render_variables(entry["text"], context)
        if isinstance(entry.get("items"), list):
            entry["items"] = [render_variables(str(item), context) for item in entry["items"]]
        if isinstance(entry.get("fields"), dict):
            entry["fields"] = {
                name: render_variables(item, context) if isinstance(item, str) else item
                for name, item in entry["fields"].items()
            }
        resolved[key] = entry
    return resolved


# ------------------------------------------------------------ the three habits
def carry_forward(
    sections: List[Dict[str, Any]], previous: Dict[str, Any]
) -> Dict[str, Any]:
    """Copy from the previous visit: only the sections marked to carry.

    The diagnosis and the standing advice come across; today's complaints and
    today's examination do not, because copying last month's findings into
    this month's record is how a chart ends up describing a patient nobody
    examined.
    """
    carried: Dict[str, Any] = {}
    for section in sections:
        if section.get("carry_forward") and section["key"] in (previous or {}):
            carried[section["key"]] = previous[section["key"]]
    return clean_values(sections, carried)


def merge_template(
    sections: List[Dict[str, Any]],
    current: Dict[str, Any],
    template: Dict[str, Any],
    *,
    replace: bool,
) -> Dict[str, Any]:
    """Load a template into a document.

    `replace` overwrites every section the template has content for. Without
    it, list items are appended and empty sections filled, so loading "knee
    advice" onto a pad that already has advice adds to it rather than wiping
    what the doctor just typed.
    """
    merged = dict(current or {})
    for section in sections:
        key = section["key"]
        incoming = (template or {}).get(key)
        if not incoming or is_empty(section, incoming):
            continue
        existing = merged.get(key)
        if replace or is_empty(section, existing):
            merged[key] = incoming
            continue
        if section["kind"] in ("list", "ai") and incoming.get("items"):
            combined = list((existing or {}).get("items") or [])
            for item in incoming["items"]:
                if item not in combined:
                    combined.append(item)
            merged[key] = {**(existing or {}), "items": combined}
        elif section["kind"] == "fields":
            fields = dict((existing or {}).get("fields") or {})
            for name, item in (incoming.get("fields") or {}).items():
                if fields.get(name) in (None, "", [], False):
                    fields[name] = item
            merged[key] = {"fields": fields}
        # A text section that already has prose is left alone without
        # `replace`: appending a paragraph into the middle of someone's
        # sentence is never what they meant.
    return clean_values(sections, merged)


# ------------------------------------------------------------------ AI drafts
_CODE_RE = re.compile(r"^[a-z]+(?:_[a-z]+)+$")


def _humanise(text: Any) -> str:
    """"severe_pain" -> "Severe pain".

    The intake stores some red flags as machine codes. A doctor reading
    "functional_impairment" on a clinical document reads it as a software
    fault, and a signed copy printing it looks like one.
    """
    value = str(text or "").strip()
    if _CODE_RE.match(value):
        value = value.replace("_", " ")
        return value[:1].upper() + value[1:]
    return value


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: List[str] = []
    for item in items:
        text = _clean_text(item, MAX_ITEM)
        if text and text.lower() not in (existing.lower() for existing in seen):
            seen.append(text)
    return seen


# ------------------------------------------------------------- intake vitals
INTAKE_VITALS = "intake:vitals"

# Intake screen field -> Visit Pad vitals field. Blood pressure is written the
# way the pad writes it, "120/80", and only when both numbers were typed.
_INTAKE_VITALS_MAP = {
    "pulse": "pulse",
    "spo2": "spo2",
    "temperature": "temperature",
    "respiration": "respiratory_rate",
    "weight": "weight",
    "height": "height",
}


def vitals_from_intake(section: Dict[str, Any], intake: Any) -> Optional[Dict[str, Any]]:
    """The vitals typed at intake, in this section's own fields. None when there are none.

    Copied as typed: nothing is converted or guessed. A reading the pad's field
    cannot hold (a number field given words) is left out rather than altered.
    """
    if section.get("kind") != "fields" or section.get("key") != "vitals" or not isinstance(intake, dict):
        return None
    specs = {spec["key"]: spec for spec in section.get("fields", [])}
    given: Dict[str, Any] = {}
    systolic = str(intake.get("bpSys") or "").strip()
    diastolic = str(intake.get("bpDia") or "").strip()
    if "bp" in specs and systolic and diastolic:
        given["bp"] = f"{systolic}/{diastolic}"
    for source, target in _INTAKE_VITALS_MAP.items():
        if target in specs:
            given[target] = intake.get(source)
    cleaned = {key: _clean_field(specs[key], value) for key, value in given.items()}
    cleaned = {key: value for key, value in cleaned.items() if value not in (None, "", [])}
    return {"fields": cleaned} if cleaned else None


def refresh_intake_vitals(
    sections: List[Dict[str, Any]],
    values: Optional[Dict[str, Any]],
    provenance: Optional[Dict[str, Any]],
    intake: Any,
) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
    """Bring a draft's vitals in line with what was saved at intake since it was opened.

    Only a vitals section that is still empty, or still exactly as copied from
    intake, is replaced. Once the doctor has typed their own readings, intake
    never overwrites them. Returns (values, provenance, changed).
    """
    values = dict(values or {})
    provenance = dict(provenance or {})
    changed = False
    for section in sections:
        key = section["key"]
        entry = vitals_from_intake(section, intake)
        if entry is None:
            continue
        origin = provenance.get(key) or {}
        untouched = origin.get("source") == INTAKE_VITALS and not origin.get("edited")
        if not (is_empty(section, values.get(key)) or untouched):
            continue
        cleaned = clean_values([section], {key: entry})[key]
        if values.get(key) == cleaned:
            continue
        values[key] = cleaned
        provenance[key] = {"source": INTAKE_VITALS, "drafted_at": datetime.now(timezone.utc).isoformat()}
        changed = True
    return values, provenance, changed




def _sentences(text: Optional[str]) -> List[str]:
    """Break a paragraph into the points it is made of."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", str(text).strip())
    return [part.strip() for part in parts if len(part.strip()) > 3]


def _background_points(record: Dict[str, Any]) -> List[str]:
    """What the patient brings with them, as the intake recorded it.

    Silence is reported as silence. "No allergies" would be a clinical claim
    nobody made; "Allergies: not asked" is the truth and tells the doctor
    there is a question still to ask.
    """
    def listed(values: Any) -> str:
        items = [str(item).strip() for item in (values or []) if str(item).strip()]
        return ", ".join(dict.fromkeys(items))

    points = []
    for label, value in (
        ("Allergies", listed(record.get("allergies"))),
        ("Already taking", listed(record.get("current_medicines"))),
        ("Past history", listed(record.get("medical_history"))),
        ("Previous surgery", listed(record.get("previous_surgeries"))),
    ):
        points.append(f"{label}: {value}" if value else f"{label}: not recorded at intake")
    return points

def draft_from_intake(
    sections: List[Dict[str, Any]], dossier: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Fill the AI sections from the intake dossier. Returns (values, provenance).

    Only sections the layout marks as AI are filled, and only from what the
    intake actually produced — an empty red-flag list stays empty rather than
    becoming "no red flags", which would be a clinical claim nobody made.
    """
    values: Dict[str, Any] = {}
    provenance: Dict[str, Any] = {}
    if not dossier:
        return values, provenance

    record = dossier.get("medical_json") or {}
    summary = dossier.get("clinical_summary") or {}
    risk = dossier.get("risk_assessment") or {}
    differential = dossier.get("differential_diagnosis") or {}
    plan = dossier.get("investigations") or {}
    drafted_at = datetime.now(timezone.utc).isoformat()

    for section in sections:
        # An investigations section takes the same suggestions, but they land
        # as suggestions rather than as advised tests: the doctor taps the
        # ones they want, and an order is placed for those alone.
        if section["kind"] == "investigations":
            if section.get("ai_source") != "suggested_investigations":
                continue
            rows = []
            seen = set()
            for item in plan.get("investigations") or []:
                if not isinstance(item, dict):
                    continue
                name = _clean_text(item.get("test"), INVESTIGATION_FIELDS["name"])
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())
                row = {"name": name}
                note = _clean_text(item.get("reason"), INVESTIGATION_FIELDS["note"])
                if note:
                    row["note"] = note
                rows.append(row)
            if rows:
                values[section["key"]] = {"investigations": [], "suggestions": rows}
                provenance[section["key"]] = {
                    "source": "ai:suggested_investigations", "drafted_at": drafted_at
                }
            continue
        if section["kind"] != "ai":
            continue
        source = section.get("ai_source")
        entry: Dict[str, Any] = {}

        if source == "intake_summary":
            # Bullets where the summariser produced them; the older prose is
            # split on sentence ends so an existing consultation still reads
            # as points rather than a paragraph.
            items = _dedupe(summary.get("history_points") or [])
            if not items:
                text = (
                    summary.get("history_of_present_illness")
                    or summary.get("summary_for_doctor")
                    or record.get("summary_for_doctor")
                    or summary.get("one_liner")
                )
                items = _dedupe(_sentences(text))
            if items:
                entry = {"items": [], "suggestions": items}
        elif source == "intake_summary_hi":
            items = _dedupe(summary.get("history_points_hi") or [])
            if items:
                entry = {"items": [], "suggestions": items}
        elif source == "background":
            items = _dedupe(_background_points(record))
            if items:
                entry = {"items": [], "suggestions": items}
        elif source == "red_flags":
            items = _dedupe(
                [_humanise(flag.get("flag", "")) for flag in risk.get("red_flags") or []
                 if isinstance(flag, dict)]
                + [_humanise(flag) for flag in record.get("red_flags") or []]
            )
            if items:
                entry = {"items": [], "suggestions": items}
        elif source == "differentials":
            items = _dedupe(
                f"{item.get('condition')} ({item.get('likelihood', 'moderate')} likelihood)"
                for item in differential.get("differentials") or []
                if isinstance(item, dict) and item.get("condition")
            )
            if items:
                entry = {"items": [], "suggestions": items}
        elif source == "suggested_investigations":
            items = _dedupe(
                item.get("test", "")
                for item in plan.get("investigations") or []
                if isinstance(item, dict)
            )
            if items:
                entry = {"items": items}

        if entry:
            values[section["key"]] = entry
            provenance[section["key"]] = {"source": f"ai:{source}", "drafted_at": drafted_at}

    # The vitals the nurse typed at intake, so the doctor does not see an
    # empty section and assume nothing was recorded.
    for section in sections:
        vitals = vitals_from_intake(section, dossier.get("vitals"))
        if vitals:
            values[section["key"]] = vitals
            provenance[section["key"]] = {"source": INTAKE_VITALS, "drafted_at": drafted_at}

    return clean_values(sections, values), provenance


def as_text(sections: List[Dict[str, Any]], values: Dict[str, Any]) -> str:
    """A signed document as plain lines, for a model to read.

    Used when drafting a discharge summary from the ward record, so the
    progress notes a doctor signed are part of what the draft is written from.
    """
    lines: List[str] = []
    for section in sections:
        value = (values or {}).get(section["key"]) or {}
        if is_empty(section, value):
            continue
        if section["kind"] == "fields":
            parts = []
            for spec in section.get("fields", []):
                item = (value.get("fields") or {}).get(spec["key"])
                if item in (None, "", [], False):
                    continue
                shown = ", ".join(item) if isinstance(item, list) else ("yes" if item is True else item)
                unit = f" {spec['unit']}" if spec.get("unit") else ""
                parts.append(f"{spec['label']} {shown}{unit}")
            lines.append(f"{section['title']}: {'; '.join(str(part) for part in parts)}")
            continue
        if value.get("text"):
            lines.append(f"{section['title']}: {value['text']}")
        if value.get("items"):
            lines.append(f"{section['title']}: {'; '.join(value['items'])}")
    return "\n".join(lines)


def draft_from_record(
    sections: List[Dict[str, Any]], record: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Copy facts already on the admission into a new document's sections.

    `record` maps a prefill source to a string or a list of strings. A value
    that is empty on the admission leaves its section empty — an allergy list
    nobody filled in is not the same as "no known allergies".
    """
    values: Dict[str, Any] = {}
    provenance: Dict[str, Any] = {}
    for section in sections:
        source = section.get("prefill_from")
        if not source:
            continue
        raw = (record or {}).get(source)
        if isinstance(raw, list):
            items = [str(item).strip() for item in raw if str(item).strip()]
        elif isinstance(raw, str) and raw.strip():
            items = [raw.strip()]
        else:
            continue
        if not items:
            continue
        if section["kind"] == "text":
            values[section["key"]] = {"text": "\n".join(items)}
        else:
            values[section["key"]] = {"items": items}
        provenance[section["key"]] = {"source": f"admission:{source}"}
    return clean_values(sections, values), provenance


# ----------------------------------------------------------------- catalogue
def normalize_phrase(text: str) -> str:
    return " ".join((text or "").lower().split())[:255]


def catalogue_phrases(
    sections: List[Dict[str, Any]], values: Dict[str, Any]
) -> List[Tuple[str, str]]:
    """The (category, phrase) pairs a saved document adds to the catalogue.

    Only short phrases are learned. A paragraph of history is one patient's
    story and would be useless — and a privacy leak — offered as a suggestion
    in the next patient's record.
    """
    phrases: List[Tuple[str, str]] = []

    def learn(category: Optional[str], text: Any) -> None:
        if not category or not isinstance(text, str):
            return
        phrase = " ".join(text.split())
        if 2 <= len(phrase) <= 120 and "{{" not in phrase:
            phrases.append((category, phrase))

    for section in sections:
        value = (values or {}).get(section["key"]) or {}
        category = section.get("catalogue_category")
        if section["kind"] in ("list", "ai"):
            for item in value.get("items") or []:
                learn(category, item)
        elif section["kind"] == "fields":
            for spec in section.get("fields", []):
                if spec.get("type") in ("text",):
                    learn(spec.get("catalogue_category"), (value.get("fields") or {}).get(spec["key"]))
    return phrases
