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
    def vitals(layout):
        return next(section for section in layout if section["key"] == "vitals")

    first = default_layout("opd_visit")
    first[0]["title"] = "changed"
    vitals(first)["fields"][0]["label"] = "changed"
    second = default_layout("opd_visit")
    assert second[0]["title"] != "changed"
    assert vitals(second)["fields"][0]["label"] != "changed"


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


def test_red_flags_do_not_print_by_default():
    """A red flag is a warning to the doctor, not a line on a patient's copy."""
    by_key = {section["key"]: section for section in _opd()}
    assert by_key["red_flags"]["visible_in_print"] is False


def test_there_is_one_list_of_conditions_not_two():
    keys = {section["key"] for section in _opd()}
    assert "differentials" not in keys
    diagnosis = next(section for section in _opd() if section["key"] == "diagnosis")
    assert diagnosis["ai_source"] == "differentials"


def test_only_the_standing_sections_carry_forward_by_default():
    """What was true last visit and is still true today.

    The doctor's own notes carry too — they are where a thought for the next
    visit is written, which is worthless if it does not survive to it. The pad
    labels a carried section with the visit it came from, so it cannot be read
    as something written today.
    """
    carried = {section["key"] for section in _opd() if section["carry_forward"]}
    # The background and the family's history are as true next visit as they
    # are today, so they come across rather than being asked again.
    assert carried == {
        "diagnosis", "advice", "advice_hi", "doctor_notes", "background",
        "family_history",
    }


def test_the_doctors_notes_stay_off_the_patients_copy():
    notes = next(section for section in _opd() if section["key"] == "doctor_notes")
    assert notes["visible_in_print"] is False


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
        {"doctor_notes": {"text": "Pain since a fall on Monday."}},
        {"doctor_notes": {"text": "Template note."}},
        replace=False,
    )
    assert merged["doctor_notes"]["text"] == "Pain since a fall on Monday."


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
    # Everything the model produced arrives as a suggestion: the section is
    # empty until the doctor taps the lines they agree with.
    assert values["intake_summary"]["items"] == []
    assert values["intake_summary"]["suggestions"] == ["Right knee pain for one month."]
    assert values["red_flags"]["suggestions"] == ["Night pain", "Weight loss"]
    # The condition alone: the model's confidence is not the doctor's, and
    # "(high likelihood)" on a signed diagnosis reads as though it were.
    assert values["diagnosis"]["suggestions"] == ["Osteoarthritis", "Gout"]
    assert values["diagnosis"]["items"] == []
    # Advised tests now arrive as suggestions the doctor taps across, never
    # as advice already given in their name.
    assert values["investigations"]["investigations"] == []
    assert [row["name"] for row in values["investigations"]["suggestions"]] == [
        "X-ray knee AP/Lat", "Uric acid",
    ]
    # The background section draws on the same dossier, so it is drafted too.
    assert set(provenance) == {
        "intake_summary", "red_flags", "diagnosis", "investigations",
    }
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
    assert values["red_flags"]["suggestions"] == ["Severe pain", "Night pain"]
    assert values["red_flags"]["items"] == []


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


# --------------------------------------------- medicines and investigations
MEDICINE_LAYOUT = [
    {"key": "medicines", "title": "Medicines", "kind": "medicines"},
]
INVESTIGATION_LAYOUT = [
    {"key": "investigations", "title": "Investigations advised",
     "kind": "investigations", "ai_source": "suggested_investigations"},
]


def test_a_medicine_keeps_the_parts_a_prescription_needs():
    cleaned = rules.clean_values(MEDICINE_LAYOUT, {
        "medicines": {"medicines": [{
            "name": "Pantoprazole", "strength": "40 mg", "form": "Tablet",
            "dosage": "1", "frequency_text": "Twice a day", "duration": "2 weeks",
            "timing": "Before food", "source": "dictated",
        }]}
    })
    row = cleaned["medicines"]["medicines"][0]
    assert row["name"] == "Pantoprazole"
    assert row["frequency_text"] == "Twice a day"
    assert row["source"] == "dictated"


def test_a_medicine_with_no_name_is_dropped():
    """A blank row on a printed prescription is worse than a lost one."""
    cleaned = rules.clean_values(MEDICINE_LAYOUT, {
        "medicines": {"medicines": [{"dosage": "1", "duration": "5 days"},
                                    {"name": "Ondansetron"}]}
    })
    assert [row["name"] for row in cleaned["medicines"]["medicines"]] == ["Ondansetron"]


def test_an_unknown_source_falls_back_to_manual():
    cleaned = rules.clean_values(MEDICINE_LAYOUT, {
        "medicines": {"medicines": [{"name": "Rabeprazole", "source": "guessed"}]}
    })
    assert cleaned["medicines"]["medicines"][0]["source"] == "manual"


def test_suggestions_are_kept_apart_from_what_is_prescribed():
    """Nothing reaches the prescription until the doctor taps it across."""
    cleaned = rules.clean_values(MEDICINE_LAYOUT, {
        "medicines": {
            "medicines": [{"name": "Pantoprazole"}],
            "suggestions": [{"name": "Domperidone", "source": "dictated"}],
        }
    })
    assert [row["name"] for row in cleaned["medicines"]["medicines"]] == ["Pantoprazole"]
    assert [row["name"] for row in cleaned["medicines"]["suggestions"]] == ["Domperidone"]


def test_a_section_holding_only_suggestions_prints_nothing():
    value = {"medicines": [], "suggestions": [{"name": "Domperidone"}]}
    assert rules.is_empty(MEDICINE_LAYOUT[0], value) is True


def test_an_accepted_medicine_is_not_empty():
    value = {"medicines": [{"name": "Pantoprazole"}], "suggestions": []}
    assert rules.is_empty(MEDICINE_LAYOUT[0], value) is False


def test_suggested_investigations_arrive_as_suggestions_not_as_orders():
    """The AI advises; the doctor decides. An order is never drafted."""
    values, provenance = rules.draft_from_intake(
        INVESTIGATION_LAYOUT,
        {"investigations": {"investigations": [
            {"test": "Ultrasound abdomen", "reason": "Right upper quadrant pain"},
            {"test": "Liver function tests"},
        ]}},
    )
    entry = values["investigations"]
    assert entry["investigations"] == []
    assert [row["name"] for row in entry["suggestions"]] == [
        "Ultrasound abdomen", "Liver function tests"
    ]
    assert entry["suggestions"][0]["note"] == "Right upper quadrant pain"
    assert provenance["investigations"]["source"] == "ai:suggested_investigations"


def test_a_medicines_section_cannot_define_fields():
    with pytest.raises(rules.LayoutError):
        rules.validate_layout([
            {"key": "medicines", "title": "Medicines", "kind": "medicines",
             "fields": [{"key": "dose", "label": "Dose"}]}
        ])


def test_the_background_fills_its_own_boxes():
    """Each answer in the box it belongs in, and a dose is not a drug name."""
    values, provenance = rules.draft_from_intake(_opd(), {"medical_json": {
        "allergies": ["Penicillin"],
        "current_medicines": [
            {"name": "Thyroxine", "dose_or_frequency": None},
            {"name": "Amlodipine", "dose_or_frequency": "5 mg at night"},
        ],
        "medical_history": ["Thyroid problem"],
    }})
    fields = values["background"]["fields"]
    assert fields["current_medicines"] == "Thyroxine, Amlodipine"
    assert fields["dosage"] == "Amlodipine: 5 mg at night"
    assert fields["past_history"] == "Thyroid problem"
    assert fields["allergies"] == "Penicillin"
    assert provenance["background"]["source"] == "ai:background"


def test_an_unanswered_question_is_left_blank_not_filled_with_none():
    """An empty box is a question still to ask; "none" would be a claim."""
    values, _ = rules.draft_from_intake(_opd(), {"medical_json": {"allergies": ["Penicillin"]}})
    assert values["background"]["fields"]["previous_surgeries"] is None
    assert values["background"]["fields"]["allergies"] == "Penicillin"


def test_the_pad_asks_after_the_family():
    section = next(item for item in _opd() if item["key"] == "family_history")
    assert section["kind"] == "list"
    assert section["carry_forward"] is True


def test_the_history_is_offered_in_hindi_as_well():
    values, _ = rules.draft_from_intake(_opd(), {"clinical_summary": {
        "history_points": ["Knee pain for one month"],
        "history_points_hi": ["एक महीने से घुटने में दर्द"],
    }})
    assert values["intake_summary"]["suggestions"] == ["Knee pain for one month"]
    assert values["intake_summary_hi"]["suggestions"] == [
        "एक महीने से घुटने में दर्द"
    ]


def test_older_prose_history_still_becomes_bullets():
    values, _ = rules.draft_from_intake(_opd(), {"clinical_summary": {
        "history_of_present_illness": "Knee pain for one month. Worse at night.",
    }})
    assert values["intake_summary"]["suggestions"] == [
        "Knee pain for one month.", "Worse at night.",
    ]


def test_advice_is_offered_from_what_the_patient_was_told():
    """The old screen's general instructions, as separate lines to tap."""
    values, provenance = rules.draft_from_intake(_opd(), {"patient_education": {
        "general_self_care": ["Drink plenty of water", "Avoid spicy food"],
        "warning_signs_return_immediately": ["Vomiting blood"],
    }})
    assert values["advice"]["items"] == []
    assert values["advice"]["suggestions"] == [
        "Drink plenty of water", "Avoid spicy food",
        "Come back at once if: Vomiting blood",
    ]
    assert provenance["advice"]["source"] == "ai:advice"


def test_advice_the_doctor_accepted_survives_a_save():
    cleaned = rules.clean_values(_opd(), {"advice": {
        "items": ["Drink plenty of water"], "suggestions": ["Avoid spicy food"],
    }})
    assert cleaned["advice"]["items"] == ["Drink plenty of water"]
    assert cleaned["advice"]["suggestions"] == ["Avoid spicy food"]
