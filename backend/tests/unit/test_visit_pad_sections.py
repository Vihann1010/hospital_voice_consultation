"""The Visit Pad's section rules, tested as plain data.

These are the rules that decide what may be written on a clinical document,
what a template overwrites, and what comes across from the last visit. None of
them need a database, so none of these tests use one.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from app.pads import sections as rules
from app.pads.defaults import DOCUMENT_TYPES, default_layout

pytestmark = pytest.mark.unit


def _opd():
    return rules.validate_layout(default_layout("opd_visit"))


# ------------------------------------------------------------------- layouts
def test_every_builtin_layout_is_valid():
    for document_type in DOCUMENT_TYPES:
        assert rules.validate_layout(default_layout(document_type))


def test_default_layout_is_a_fresh_copy_each_time():
    first = default_layout("opd_visit")
    first[0]["title"] = "changed"
    first[3]["fields"][0]["label"] = "changed"
    second = default_layout("opd_visit")
    assert second[0]["title"] != "changed"
    assert second[3]["fields"][0]["label"] != "changed"


@pytest.mark.parametrize(
    "sections, message",
    [
        ([], "at least one section"),
        ([{"key": "a", "title": "A", "kind": "text"}, {"key": "a", "title": "B", "kind": "list"}],
         "share the key"),
        ([{"key": "v", "title": "Vitals", "kind": "fields"}], "defines none"),
        ([{"key": "r", "title": "Red flags", "kind": "ai"}], "drafted from"),
        ([{"key": "n", "title": "Notes", "kind": "text", "ai_source": "red_flags"}], "Only an AI"),
        ([{"key": "Bad Key", "title": "X", "kind": "text"}], "lower-case"),
        ([{"key": "s", "title": "S", "kind": "fields",
           "fields": [{"key": "side", "label": "Side", "type": "select"}]}], "no options"),
    ],
)
def test_invalid_layouts_are_refused_with_a_reason(sections, message):
    with pytest.raises(rules.LayoutError, match=message):
        rules.validate_layout(sections)


def test_differentials_do_not_print_by_default():
    by_key = {section["key"]: section for section in _opd()}
    assert by_key["differentials"]["visible_in_print"] is False
    assert by_key["red_flags"]["visible_in_print"] is False


def test_only_diagnosis_and_advice_carry_forward_by_default():
    carried = {section["key"] for section in _opd() if section["carry_forward"]}
    assert carried == {"diagnosis", "advice"}


# -------------------------------------------------------------------- values
def test_values_are_coerced_to_their_field_types():
    layout = rules.validate_layout([
        {"key": "vitals", "title": "Vitals", "kind": "fields", "fields": [
            {"key": "pulse", "label": "Pulse", "type": "number"},
            {"key": "temp", "label": "Temp", "type": "number"},
            {"key": "seen", "label": "Seen", "type": "date"},
            {"key": "side", "label": "Side", "type": "select", "options": ["Left", "Right"]},
            {"key": "tags", "label": "Tags", "type": "multiselect", "options": ["a", "b"]},
            {"key": "fasting", "label": "Fasting", "type": "checkbox"},
        ]},
    ])
    cleaned = rules.clean_values(layout, {"vitals": {"fields": {
        "pulse": "88", "temp": "98.64", "seen": "2026-09-13T10:00:00",
        "side": "Middle", "tags": ["a", "z"], "fasting": 1,
    }}})["vitals"]["fields"]
    assert cleaned == {
        "pulse": 88, "temp": 98.64, "seen": "2026-09-13",
        "side": None, "tags": ["a"], "fasting": True,
    }


def test_nonsense_numbers_and_dates_become_empty_not_errors():
    layout = rules.validate_layout([
        {"key": "f", "title": "F", "kind": "fields", "fields": [
            {"key": "n", "label": "N", "type": "number"},
            {"key": "d", "label": "D", "type": "date"},
        ]},
    ])
    cleaned = rules.clean_values(layout, {"f": {"fields": {"n": "eighty", "d": "yesterday"}}})
    assert cleaned["f"]["fields"] == {"n": None, "d": None}


def test_unknown_sections_are_dropped_and_list_items_deduplicated():
    cleaned = rules.clean_values(_opd(), {
        "complaints": {"items": ["Knee pain", "Knee pain", "  ", "Swelling"]},
        "not_a_section": {"text": "ignored"},
    })
    assert cleaned == {"complaints": {"items": ["Knee pain", "Swelling"]}}


def test_is_empty_treats_a_blank_vitals_section_as_empty():
    vitals = next(section for section in _opd() if section["key"] == "vitals")
    assert rules.is_empty(vitals, {"fields": {"bp": None, "pulse": None}})
    assert not rules.is_empty(vitals, {"fields": {"bp": "130/80", "pulse": None}})


# ------------------------------------------------------------------ habits
def test_copy_from_previous_visit_takes_only_carry_forward_sections():
    previous = {
        "complaints": {"items": ["Knee pain"]},
        "examination": {"items": ["Crepitus"]},
        "diagnosis": {"items": ["B/L OA knee"]},
        "advice": {"items": ["Quadriceps exercises"]},
    }
    carried = rules.carry_forward(_opd(), previous)
    assert set(carried) == {"diagnosis", "advice"}


def test_loading_a_template_appends_to_lists_without_replace():
    layout = _opd()
    merged = rules.merge_template(
        layout,
        {"advice": {"items": ["Rest"]}},
        {"advice": {"items": ["Ice", "Rest"]}},
        replace=False,
    )
    assert merged["advice"]["items"] == ["Rest", "Ice"]


def test_loading_a_template_never_rewrites_prose_already_typed():
    layout = _opd()
    merged = rules.merge_template(
        layout,
        {"history": {"text": "Pain since a fall on Monday."}},
        {"history": {"text": "Template history."}},
        replace=False,
    )
    assert merged["history"]["text"] == "Pain since a fall on Monday."


def test_replace_overwrites_sections_the_template_fills():
    layout = _opd()
    merged = rules.merge_template(
        layout,
        {"advice": {"items": ["Rest"]}, "diagnosis": {"items": ["Sprain"]}},
        {"advice": {"items": ["Ice"]}},
        replace=True,
    )
    assert merged["advice"]["items"] == ["Ice"]
    assert merged["diagnosis"]["items"] == ["Sprain"]


# --------------------------------------------------------------- variables
def test_variables_resolve_and_typos_stay_visible():
    patient = SimpleNamespace(
        name="Paras Nath", uhid="SAT26AAAAAC", age=79,
        gender=SimpleNamespace(value="male"), address="12 Civil Lines", city="Kanpur",
        guardian_name="Ram Nath", guardian_relation="S/O",
    )
    context = rules.variable_context(patient, date(2026, 9, 13))
    text = rules.render_variables(
        "{{patient_name}} ({{uhid}}), {{age}} y {{sex}}, {{guardian}}, {{address}}, "
        "seen {{date}}. {{patinet_name}}",
        context,
    )
    assert text == (
        "Paras Nath (SAT26AAAAAC), 79 y Male, S/O Ram Nath, 12 Civil Lines, Kanpur, "
        "seen 13 Sep 2026. {{patinet_name}}"
    )


# ------------------------------------------------------------------ AI drafts
DOSSIER = {
    "medical_json": {"red_flags": ["Night pain", "night pain"], "summary_for_doctor": "x"},
    "clinical_summary": {"history_of_present_illness": "Right knee pain for one month."},
    "risk_assessment": {"red_flags": [{"flag": "Night pain"}, {"flag": "Weight loss"}]},
    "differential_diagnosis": {"differentials": [
        {"condition": "Osteoarthritis", "likelihood": "high"},
        {"condition": "Gout", "likelihood": "low"},
    ]},
    "investigations": {"investigations": [{"test": "X-ray knee AP/Lat"}, {"test": "Uric acid"}]},
}


def test_ai_sections_are_drafted_from_the_intake_and_marked():
    values, provenance = rules.draft_from_intake(_opd(), DOSSIER)
    assert values["intake_summary"]["text"] == "Right knee pain for one month."
    assert values["red_flags"]["items"] == ["Night pain", "Weight loss"]
    assert values["differentials"]["items"] == [
        "Osteoarthritis (high likelihood)", "Gout (low likelihood)",
    ]
    assert values["investigations"]["items"] == ["X-ray knee AP/Lat", "Uric acid"]
    assert set(provenance) == {"intake_summary", "red_flags", "differentials", "investigations"}
    assert all(origin["source"].startswith("ai:") for origin in provenance.values())


def test_no_red_flags_from_intake_leaves_the_section_empty_not_reassuring():
    values, provenance = rules.draft_from_intake(_opd(), {"risk_assessment": {"red_flags": []}})
    assert "red_flags" not in values
    assert "red_flags" not in provenance


def test_no_dossier_drafts_nothing():
    assert rules.draft_from_intake(_opd(), None) == ({}, {})


# --------------------------------------------------------------- catalogue
def test_catalogue_learns_short_phrases_only():
    layout = _opd()
    phrases = rules.catalogue_phrases(layout, {
        "diagnosis": {"items": ["B/L OA knee"]},
        "advice": {"items": ["x" * 200, "Hot fomentation", "{{patient_name}} to rest"]},
        "history": {"text": "A long paragraph of one patient's story that must not be learned."},
    })
    assert ("diagnosis", "B/L OA knee") in phrases
    assert ("advice", "Hot fomentation") in phrases
    assert all(len(text) <= 120 for _, text in phrases)
    assert not any("{{" in text for _, text in phrases)
    assert not any(category is None for category, _ in phrases)


def test_normalised_phrases_collapse_case_and_spacing():
    assert rules.normalize_phrase("  B/L  OA   Knee ") == "b/l oa knee"


def test_intake_flag_codes_are_shown_as_words():
    values, _ = rules.draft_from_intake(
        _opd(), {"medical_json": {"red_flags": ["severe_pain", "Night pain", "Severe pain"]}}
    )
    assert values["red_flags"]["items"] == ["Severe pain", "Night pain"]


# ------------------------------------------------------------- intake vitals
def test_intake_vitals_are_copied_into_the_pad_as_typed():
    values, provenance = rules.draft_from_intake(_opd(), {"vitals": {
        "bpSys": "120", "bpDia": "70", "spo2": "92", "pulse": "", "temperature": "98.6", "weight": "abc"}})
    fields = values["vitals"]["fields"]
    assert fields["bp"] == "120/70"
    assert fields["spo2"] == 92
    assert fields["temperature"] == 98.6
    assert fields["pulse"] is None
    assert fields["weight"] is None  # words in a number field are left out, not altered
    assert provenance["vitals"]["source"] == rules.INTAKE_VITALS


def test_half_a_blood_pressure_is_not_written():
    values, provenance = rules.draft_from_intake(_opd(), {"vitals": {"bpSys": "120", "bpDia": ""}})
    assert "vitals" not in values
    assert "vitals" not in provenance


def test_refreshed_intake_vitals_never_overwrite_the_doctors_readings():
    sections = _opd()
    values, provenance, changed = rules.refresh_intake_vitals(sections, {}, {}, {"spo2": "95"})
    assert changed and values["vitals"]["fields"]["spo2"] == 95

    values, provenance, changed = rules.refresh_intake_vitals(sections, values, provenance, {"spo2": "97"})
    assert changed and values["vitals"]["fields"]["spo2"] == 97

    _, _, changed = rules.refresh_intake_vitals(sections, values, provenance, {"spo2": "97"})
    assert not changed

    edited = {**provenance, "vitals": {**provenance["vitals"], "edited": True}}
    _, _, changed = rules.refresh_intake_vitals(sections, values, edited, {"spo2": "90"})
    assert not changed

    typed_by_doctor = {"vitals": {"fields": {"pulse": 80}}}
    _, _, changed = rules.refresh_intake_vitals(sections, typed_by_doctor, {}, {"spo2": "90"})
    assert not changed


def test_validated_builtin_layout_carries_every_switch():
    # Regression: the built-in layout once reached the browser without these
    # keys, and a section missing `visible_in_pad` was hidden — so the whole
    # pad rendered empty.
    for section in _opd():
        assert {"visible_in_pad", "visible_in_print", "carry_forward", "fields"} <= set(section)
