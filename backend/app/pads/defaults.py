"""Document types, and the layout each one has before anyone edits it.

A document type answers four questions the engine cannot guess:

  scope      does it belong to an OPD consultation or an inpatient admission
  many       one per admission (the discharge summary) or many (progress notes)
  authority  is it the doctor's document or the nurse's — which decides who may
             write it and who may sign it
  sections   what it looks like until an administrator saves a layout for it

The layouts here are the fallback, not the configuration. The moment a layout
is saved for a document type, that saved layout is used instead. Keeping the
defaults in code means a new kind of document works on the day it ships.

Judgements worth stating, because they are clinical rather than technical:

* **Differentials do not print by default.** They are the copilot's reasoning
  for the doctor. On a patient's copy "possible septic arthritis (low
  likelihood)" reads as a diagnosis and frightens someone who has a sprain.
* **Carry-forward is for what persists.** Diagnosis, standing advice, past
  history, allergies, and a progress note's assessment and plan — which is
  most of what yesterday's note is for. Complaints, examination and vitals are
  today's, and copying them forward is how a chart comes to describe an
  examination nobody performed.
* **Nursing documents are the nurse's.** A nurse writes and signs the initial
  assessment and each shift's note. They are not drafts awaiting a doctor.
* **The inpatient drug chart is not a pad form.** Prescribing and the record of
  each dose given or omitted already exist as structured data with a schedule,
  and flattening that into a document would lose exactly what the ward needs.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from app.pads import forms
from app.theatre.rules import ANAESTHESIA_TYPES

#: "patient" documents stand alone: certificates and consent forms, which may
#: be linked to a visit, an admission or a surgery but belong to none of them.
Scope = Literal["consultation", "admission", "surgery", "patient"]
Authority = Literal["doctor", "nursing"]


@dataclass(frozen=True)
class DocumentType:
    key: str
    label: str
    scope: Scope
    authority: Authority
    many: bool = False
    sections: List[Dict[str, Any]] = field(default_factory=list)
    #: "certificate" or "consent": numbered, checked and printed by app/pads/forms.
    family: Optional[str] = None
    #: A link the document cannot be written without, e.g. "admission".
    requires: Optional[str] = None


def _vitals(*extra: Dict[str, Any], title: str = "Vitals") -> Dict[str, Any]:
    return {
        "key": "vitals",
        "title": title,
        "kind": "fields",
        "fields": [
            {"key": "bp", "label": "BP", "type": "text", "unit": "mmHg"},
            {"key": "pulse", "label": "Pulse", "type": "number", "unit": "/min"},
            {"key": "temperature", "label": "Temp", "type": "number", "unit": "°F"},
            {"key": "respiratory_rate", "label": "RR", "type": "number", "unit": "/min"},
            {"key": "spo2", "label": "SpO2", "type": "number", "unit": "%"},
            *extra,
        ],
    }


_ABSENT_PRESENT = ["Absent", "Present"]

# ------------------------------------------------------------------ OPD
_OPD_VISIT: List[Dict[str, Any]] = [
    {"key": "intake_summary", "title": "History from intake", "kind": "ai",
     "ai_source": "intake_summary", "visible_in_print": True},
    {"key": "complaints", "title": "Chief complaints", "kind": "list",
     "catalogue_category": "complaint", "placeholder": "Add a complaint"},
    {"key": "history", "title": "History", "kind": "text",
     "placeholder": "Onset, progression, relevant history"},
    {
        "key": "vitals",
        "title": "Vitals",
        "kind": "fields",
        "fields": [
            {"key": "bp", "label": "BP", "type": "text", "unit": "mmHg"},
            {"key": "pulse", "label": "Pulse", "type": "number", "unit": "/min"},
            {"key": "temperature", "label": "Temp", "type": "number", "unit": "°F"},
            {"key": "spo2", "label": "SpO2", "type": "number", "unit": "%"},
            {"key": "weight", "label": "Weight", "type": "number", "unit": "kg"},
            {"key": "height", "label": "Height", "type": "number", "unit": "cm"},
        ],
    },
    {"key": "examination", "title": "Examination", "kind": "list",
     "catalogue_category": "examination", "placeholder": "Add a finding"},
    {"key": "red_flags", "title": "Red flags", "kind": "ai",
     "ai_source": "red_flags", "visible_in_print": False},
    {"key": "differentials", "title": "Differential diagnosis", "kind": "ai",
     "ai_source": "differentials", "visible_in_print": False},
    {"key": "diagnosis", "title": "Diagnosis", "kind": "list",
     "catalogue_category": "diagnosis", "carry_forward": True,
     "placeholder": "Add a diagnosis"},
    {"key": "investigations", "title": "Investigations advised", "kind": "ai",
     "ai_source": "suggested_investigations", "catalogue_category": "investigation"},
    {"key": "advice", "title": "Advice", "kind": "list",
     "catalogue_category": "advice", "carry_forward": True, "placeholder": "Add advice"},
    {
        "key": "follow_up",
        "title": "Follow-up",
        "kind": "fields",
        "fields": [
            {"key": "date", "label": "Review on", "type": "date"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
]

# ------------------------------------------------------------ inpatient
_ADMISSION_NOTE: List[Dict[str, Any]] = [
    {"key": "presenting_complaint", "title": "Presenting complaint", "kind": "list",
     "catalogue_category": "complaint", "prefill_from": "reason_for_admission",
     "placeholder": "Add a complaint"},
    {"key": "history", "title": "History of present illness", "kind": "text"},
    {"key": "past_history", "title": "Past history", "kind": "list",
     "catalogue_category": "past_history", "carry_forward": True,
     "placeholder": "Diabetes, hypertension, previous surgery…"},
    {"key": "allergies", "title": "Allergies", "kind": "list",
     "catalogue_category": "allergy", "prefill_from": "allergies", "carry_forward": True,
     "placeholder": "Add an allergy"},
    {
        "key": "general_examination",
        "title": "General examination",
        "kind": "fields",
        "fields": [
            {"key": "consciousness", "label": "Consciousness", "type": "select",
             "options": ["Conscious, oriented", "Drowsy", "Unconscious"]},
            {"key": "pallor", "label": "Pallor", "type": "select", "options": _ABSENT_PRESENT},
            {"key": "icterus", "label": "Icterus", "type": "select", "options": _ABSENT_PRESENT},
            {"key": "cyanosis", "label": "Cyanosis", "type": "select", "options": _ABSENT_PRESENT},
            {"key": "oedema", "label": "Oedema", "type": "select", "options": _ABSENT_PRESENT},
        ],
    },
    _vitals(),
    {"key": "systemic_examination", "title": "Systemic and local examination",
     "kind": "list", "catalogue_category": "examination", "placeholder": "Add a finding"},
    {"key": "provisional_diagnosis", "title": "Provisional diagnosis", "kind": "list",
     "catalogue_category": "diagnosis", "prefill_from": "provisional_diagnosis",
     "placeholder": "Add a diagnosis"},
    {"key": "plan", "title": "Plan", "kind": "list", "catalogue_category": "plan",
     "placeholder": "Investigations, treatment, consults"},
]

_PROGRESS_NOTE: List[Dict[str, Any]] = [
    {"key": "subjective", "title": "Patient reports", "kind": "text",
     "placeholder": "How the patient says they are today"},
    _vitals(),
    {"key": "examination", "title": "Examination", "kind": "list",
     "catalogue_category": "examination", "placeholder": "Add a finding"},
    {"key": "assessment", "title": "Assessment", "kind": "list",
     "catalogue_category": "diagnosis", "carry_forward": True,
     "placeholder": "Working diagnosis, progress"},
    {"key": "plan", "title": "Plan", "kind": "list", "catalogue_category": "plan",
     "carry_forward": True, "placeholder": "Add to the plan"},
]

_NURSING_ASSESSMENT: List[Dict[str, Any]] = [
    {
        "key": "arrival",
        "title": "Arrival on the ward",
        "kind": "fields",
        "fields": [
            {"key": "mode", "label": "Arrived by", "type": "select",
             "options": ["Walking", "Wheelchair", "Stretcher", "Ambulance"]},
            {"key": "accompanied_by", "label": "Accompanied by", "type": "text"},
            {"key": "id_band", "label": "ID band applied", "type": "checkbox"},
        ],
    },
    _vitals(
        {"key": "weight", "label": "Weight", "type": "number", "unit": "kg"},
        {"key": "pain", "label": "Pain score", "type": "number", "unit": "/10"},
        title="Vitals on admission",
    ),
    {"key": "allergies", "title": "Allergies", "kind": "list",
     "catalogue_category": "allergy", "prefill_from": "allergies",
     "placeholder": "Add an allergy"},
    {
        "key": "fall_risk",
        "title": "Fall risk",
        "kind": "fields",
        "fields": [
            {"key": "risk", "label": "Risk", "type": "select", "options": ["Low", "Moderate", "High"]},
            {"key": "precautions", "label": "Precautions", "type": "multiselect",
             "options": ["Side rails up", "Bed at lowest height", "Call bell within reach",
                         "Attendant at bedside"]},
        ],
    },
    {
        "key": "skin",
        "title": "Skin and pressure areas",
        "kind": "fields",
        "fields": [
            {"key": "pressure_risk", "label": "Pressure sore risk", "type": "select",
             "options": ["Low", "Moderate", "High"]},
            {"key": "wounds", "label": "Wounds or existing sores", "type": "text"},
        ],
    },
    {
        "key": "lines",
        "title": "Lines and devices",
        "kind": "fields",
        "fields": [
            {"key": "devices", "label": "In place", "type": "multiselect",
             "options": ["IV cannula", "Urinary catheter", "Ryles tube", "Oxygen", "Drain"]},
            {"key": "notes", "label": "Site, size, date inserted", "type": "text"},
        ],
    },
    {
        "key": "diet",
        "title": "Diet",
        "kind": "fields",
        "fields": [
            {"key": "diet", "label": "Diet", "type": "select",
             "options": ["Normal", "Soft", "Liquid", "Diabetic", "Nil by mouth"]},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
    {"key": "valuables", "title": "Valuables and belongings", "kind": "text",
     "placeholder": "What was handed over, and to whom"},
    {"key": "nursing_plan", "title": "Nursing care plan", "kind": "list",
     "catalogue_category": "nursing_plan", "placeholder": "Add to the care plan"},
]

_NURSING_NOTE: List[Dict[str, Any]] = [
    {
        "key": "shift",
        "title": "Shift",
        "kind": "fields",
        "fields": [
            {"key": "shift", "label": "Shift", "type": "select", "required": True,
             "options": ["Morning", "Evening", "Night"]},
        ],
    },
    {"key": "observations", "title": "Observations", "kind": "text",
     "placeholder": "How the patient was through the shift"},
    {"key": "care_given", "title": "Care given", "kind": "list",
     "catalogue_category": "nursing_care", "placeholder": "Dressing, positioning, catheter care…"},
    {"key": "concerns", "title": "Concerns escalated", "kind": "list",
     "catalogue_category": "nursing_concern", "placeholder": "What was reported, to whom"},
    {"key": "handover", "title": "For the next shift", "kind": "text"},
]

_DISCHARGE_SUMMARY: List[Dict[str, Any]] = [
    {"key": "final_diagnosis", "title": "Final diagnosis", "kind": "list",
     "catalogue_category": "diagnosis", "prefill_from": "final_diagnosis",
     "placeholder": "Add a diagnosis"},
    {"key": "presenting_complaint", "title": "Presenting complaint", "kind": "text",
     "prefill_from": "reason_for_admission"},
    {"key": "hospital_course", "title": "Course in hospital", "kind": "text"},
    {"key": "significant_findings", "title": "Significant findings", "kind": "text"},
    {"key": "procedures", "title": "Procedures performed", "kind": "list",
     "catalogue_category": "procedure", "placeholder": "Add a procedure"},
    {
        "key": "condition_at_discharge",
        "title": "Condition at discharge",
        "kind": "fields",
        "fields": [
            {"key": "condition", "label": "Condition", "type": "select", "required": True,
             "options": ["Stable", "Improved", "Unchanged", "Referred"]},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
    {"key": "discharge_medications", "title": "Medicines on discharge", "kind": "list",
     "catalogue_category": "discharge_medicine",
     "placeholder": "Name, dose, how often, for how long"},
    {"key": "diet_and_activity", "title": "Diet and activity", "kind": "text"},
    {
        "key": "follow_up",
        "title": "Follow-up",
        "kind": "fields",
        "fields": [
            {"key": "date", "label": "Review on", "type": "date"},
            {"key": "notes", "label": "With whom, and what to bring", "type": "text"},
        ],
    },
    {"key": "warning_signs", "title": "Come back immediately if", "kind": "list",
     "catalogue_category": "warning_sign", "placeholder": "Add a warning sign"},
]


# ----------------------------------------------------------------- theatre
_PRE_OP_CHECKLIST: List[Dict[str, Any]] = [
    {"key": "procedure", "title": "Procedure and side as booked", "kind": "text",
     "prefill_from": "procedure"},
    {
        "key": "checks",
        "title": "Checks",
        "kind": "fields",
        "fields": [
            {"key": "identity_confirmed", "label": "Identity confirmed with the patient",
             "type": "checkbox", "required": True},
            {"key": "consent_signed", "label": "Consent form signed", "type": "checkbox",
             "required": True},
            {"key": "site_marked", "label": "Operation site marked", "type": "checkbox",
             "required": True},
            {"key": "anaesthesia_consent", "label": "Anaesthesia consent signed", "type": "checkbox"},
        ],
    },
    {
        "key": "fasting",
        "title": "Fasting",
        "kind": "fields",
        "fields": [
            {"key": "last_solids", "label": "Last solids at", "type": "text"},
            {"key": "last_fluids", "label": "Last clear fluids at", "type": "text"},
        ],
    },
    {"key": "allergies", "title": "Allergies", "kind": "list", "catalogue_category": "allergy",
     "prefill_from": "allergies", "placeholder": "Add an allergy"},
    _vitals(title="Vitals before shifting"),
    {
        "key": "preparation",
        "title": "Preparation",
        "kind": "fields",
        "fields": [
            {"key": "done", "label": "Done", "type": "multiselect",
             "options": ["Jewellery removed", "Dentures removed", "Nail polish removed",
                         "Bladder emptied", "Skin prepared", "Pre-medication given",
                         "IV line in place"]},
        ],
    },
    {
        "key": "blood",
        "title": "Blood and reports",
        "kind": "fields",
        "fields": [
            {"key": "blood", "label": "Blood", "type": "select",
             "options": ["Not required", "Grouped and saved", "Cross-matched units ready"]},
            {"key": "reports_with_patient", "label": "Reports and films sent with the patient",
             "type": "checkbox"},
        ],
    },
    {"key": "notes", "title": "Notes for theatre", "kind": "text"},
]

_PRE_ANAESTHETIC: List[Dict[str, Any]] = [
    {"key": "procedure", "title": "Planned procedure", "kind": "text", "prefill_from": "procedure"},
    {"key": "history", "title": "Relevant history", "kind": "list",
     "catalogue_category": "past_history", "placeholder": "Diabetes, asthma, previous anaesthesia…"},
    {"key": "current_medicines", "title": "Current medicines", "kind": "list",
     "catalogue_category": "discharge_medicine"},
    {"key": "allergies", "title": "Allergies", "kind": "list", "catalogue_category": "allergy",
     "prefill_from": "allergies"},
    _vitals({"key": "weight", "label": "Weight", "type": "number", "unit": "kg"}),
    {
        "key": "airway",
        "title": "Airway and grading",
        "kind": "fields",
        "fields": [
            {"key": "asa", "label": "ASA grade", "type": "select", "required": True,
             "options": ["ASA I", "ASA II", "ASA III", "ASA IV", "ASA V", "ASA VI"]},
            {"key": "mallampati", "label": "Mallampati", "type": "select",
             "options": ["I", "II", "III", "IV"]},
            {"key": "mouth_opening", "label": "Mouth opening", "type": "select",
             "options": ["Adequate", "Restricted"]},
            {"key": "neck", "label": "Neck movement", "type": "select",
             "options": ["Normal", "Restricted"]},
        ],
    },
    {"key": "investigations", "title": "Investigations reviewed", "kind": "text"},
    {
        "key": "plan",
        "title": "Anaesthesia plan",
        "kind": "fields",
        "fields": [
            {"key": "technique", "label": "Technique", "type": "select", "options": ANAESTHESIA_TYPES},
            {"key": "fitness", "label": "Fitness", "type": "select", "required": True,
             "options": ["Fit", "Fit — higher risk explained", "Not fit — postpone"]},
            {"key": "notes", "label": "Notes", "type": "textarea"},
        ],
    },
]

_DAY_PROCEDURE_CHECKLIST: List[Dict[str, Any]] = [
    # The surgical checklist asks for the operation site to be marked, and marks
    # it required. A gastroscopy has no site to mark, so the only way through it
    # is to tick a box that is not true — which is how a ward learns that the
    # checks are paperwork. This is the same checklist with the questions that
    # actually decide whether a day case can go ahead: consent, fasting, what
    # the patient stopped taking, and who is taking them home afterwards.
    {"key": "procedure", "title": "Procedure as booked", "kind": "text",
     "prefill_from": "procedure"},
    {
        "key": "checks",
        "title": "Checks",
        "kind": "fields",
        "fields": [
            {"key": "identity_confirmed", "label": "Identity confirmed with the patient",
             "type": "checkbox", "required": True},
            {"key": "consent_signed", "label": "Consent form signed", "type": "checkbox",
             "required": True},
            {"key": "fasting_confirmed", "label": "Fasting confirmed with the patient",
             "type": "checkbox", "required": True},
            # Sedation is why this one matters: a patient who came here alone
            # cannot be sent home alone, and that is found out at the door or
            # not at all.
            {"key": "escort_present", "label": "Escort present to take the patient home",
             "type": "checkbox"},
            {"key": "sedation_consent", "label": "Sedation explained and consented",
             "type": "checkbox"},
        ],
    },
    {
        "key": "fasting",
        "title": "Fasting",
        "kind": "fields",
        "fields": [
            {"key": "last_solids", "label": "Last solids at", "type": "text"},
            {"key": "last_fluids", "label": "Last clear fluids at", "type": "text"},
        ],
    },
    {
        "key": "medicines_held",
        "title": "Medicines held or adjusted",
        "kind": "fields",
        "fields": [
            {"key": "anticoagulant", "label": "Blood thinner", "type": "select",
             "options": ["None", "Stopped as advised", "Still taking — tell the endoscopist"]},
            {"key": "diabetes", "label": "Diabetes medicines", "type": "select",
             "options": ["None", "Withheld this morning", "Taken — tell the endoscopist"]},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
    {
        "key": "preparation",
        "title": "Preparation",
        "kind": "fields",
        "fields": [
            {"key": "bowel_prep", "label": "Bowel preparation (lower GI only)", "type": "select",
             "options": ["Not applicable", "Adequate", "Inadequate — tell the endoscopist"]},
            {"key": "done", "label": "Done", "type": "multiselect",
             "options": ["Dentures removed", "Jewellery removed", "Bladder emptied",
                         "IV line in place", "Consent copy filed"]},
        ],
    },
    {"key": "allergies", "title": "Allergies", "kind": "list", "catalogue_category": "allergy",
     "prefill_from": "allergies", "placeholder": "Add an allergy"},
    _vitals(title="Vitals before the procedure"),
    {"key": "notes", "title": "Notes", "kind": "text"},
]

_ENDOSCOPY_REPORT: List[Dict[str, Any]] = [
    {"key": "procedure", "title": "Procedure", "kind": "text", "prefill_from": "procedure"},
    {"key": "indication", "title": "Indication", "kind": "list",
     "catalogue_category": "diagnosis", "prefill_from": "diagnosis"},
    {
        "key": "conduct",
        "title": "How it was done",
        "kind": "fields",
        "fields": [
            {"key": "sedation", "label": "Sedation", "type": "select",
             "options": ["None", "Topical throat spray", "Conscious sedation", "Deep sedation",
                         "General anaesthesia"]},
            {"key": "extent", "label": "Extent reached", "type": "text",
             "placeholder": "Second part of duodenum / caecum / terminal ileum"},
            {"key": "tolerance", "label": "Patient tolerance", "type": "select",
             "options": ["Well tolerated", "Fair", "Poor — procedure curtailed"]},
            {"key": "complications", "label": "Complications", "type": "text",
             "placeholder": "None, or say what happened"},
        ],
    },
    {"key": "findings", "title": "Findings", "kind": "text",
     "placeholder": "By region, in the order examined"},
    # Endoscopy images are attached to the patient's record as clinical
    # photographs (app/services/patient_file_service.py), which already handles
    # upload, access and withdrawal. What belongs on the report is the count,
    # so a reader knows whether to go looking for them.
    {"key": "images", "title": "Images", "kind": "fields",
     "fields": [
         {"key": "taken", "label": "Images taken", "type": "number"},
         {"key": "filed", "label": "Filed to the patient's record", "type": "checkbox"},
     ]},
    {
        "key": "specimen",
        "title": "Specimen",
        "kind": "fields",
        "fields": [
            # Ticking this raises the histopathology order on signing, so the
            # outside laboratory's report comes back against this patient
            # instead of arriving as loose paper weeks later.
            {"key": "biopsy_taken", "label": "Biopsy taken and sent for histopathology",
             "type": "checkbox"},
            {"key": "site", "label": "Site and number of pieces", "type": "text"},
            {"key": "rapid_urease", "label": "Rapid urease test", "type": "select",
             "options": ["Not done", "Positive", "Negative"]},
        ],
    },
    {"key": "diagnosis", "title": "Endoscopic diagnosis", "kind": "list",
     "catalogue_category": "diagnosis"},
    {"key": "advice", "title": "Advice", "kind": "text"},
    {
        "key": "review",
        "title": "Review",
        "kind": "fields",
        "fields": [
            {"key": "date", "label": "Review on", "type": "date"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
]

_OPERATION_NOTE: List[Dict[str, Any]] = [
    {"key": "procedure", "title": "Procedure", "kind": "text", "prefill_from": "procedure"},
    {"key": "team", "title": "Team", "kind": "text", "prefill_from": "team"},
    {"key": "pre_op_diagnosis", "title": "Pre-operative diagnosis", "kind": "list",
     "catalogue_category": "diagnosis", "prefill_from": "diagnosis"},
    {"key": "post_op_diagnosis", "title": "Post-operative diagnosis", "kind": "list",
     "catalogue_category": "diagnosis"},
    {"key": "position", "title": "Position and approach", "kind": "text"},
    {"key": "findings", "title": "Findings", "kind": "text"},
    {"key": "steps", "title": "Procedure details", "kind": "text"},
    {"key": "implants", "title": "Implants used", "kind": "list", "catalogue_category": "implant",
     "placeholder": "Make, size, lot number"},
    {
        "key": "measures",
        "title": "Blood loss, drains, specimens",
        "kind": "fields",
        "fields": [
            {"key": "blood_loss_ml", "label": "Estimated blood loss", "type": "number", "unit": "ml"},
            {"key": "drains", "label": "Drains", "type": "text"},
            {"key": "specimens", "label": "Specimens sent", "type": "text"},
        ],
    },
    {"key": "complications", "title": "Complications", "kind": "list",
     "catalogue_category": "complication", "placeholder": "None, or what happened"},
    {"key": "closure", "title": "Closure", "kind": "text"},
    {"key": "instructions", "title": "Post-operative instructions", "kind": "list",
     "catalogue_category": "post_op_instruction"},
]

_POST_OP_ORDERS: List[Dict[str, Any]] = [
    {"key": "procedure", "title": "Procedure", "kind": "text", "prefill_from": "procedure"},
    {
        "key": "monitoring",
        "title": "Monitoring",
        "kind": "fields",
        "fields": [
            {"key": "vitals_every", "label": "Vitals every", "type": "select",
             "options": ["15 minutes", "30 minutes", "1 hour", "4 hours"]},
            {"key": "position", "label": "Position", "type": "text"},
            {"key": "oxygen", "label": "Oxygen", "type": "text"},
        ],
    },
    {
        "key": "diet",
        "title": "Diet",
        "kind": "fields",
        "fields": [
            {"key": "nil_by_mouth_until", "label": "Nil by mouth until", "type": "text"},
            {"key": "then", "label": "Then", "type": "select",
             "options": ["Sips of water", "Clear liquids", "Soft diet", "Normal diet"]},
        ],
    },
    {"key": "fluids", "title": "IV fluids", "kind": "list", "catalogue_category": "iv_fluid"},
    {"key": "orders", "title": "Orders", "kind": "list", "catalogue_category": "post_op_order",
     "placeholder": "Prescribe medicines on the drug chart; list other orders here"},
    {"key": "watch_for", "title": "Call the doctor if", "kind": "list",
     "catalogue_category": "warning_sign"},
    {"key": "mobilisation", "title": "Mobilisation", "kind": "text"},
    {
        "key": "review",
        "title": "Review",
        "kind": "fields",
        "fields": [
            {"key": "date", "label": "Review on", "type": "date"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
]


REGISTRY: Dict[str, DocumentType] = {
    spec.key: spec
    for spec in (
        DocumentType("opd_visit", "OPD visit pad", "consultation", "doctor",
                     sections=_OPD_VISIT),
        DocumentType("ipd_admission_note", "Admission note", "admission", "doctor",
                     sections=_ADMISSION_NOTE),
        DocumentType("ipd_progress_note", "Progress note", "admission", "doctor",
                     many=True, sections=_PROGRESS_NOTE),
        DocumentType("ipd_nursing_assessment", "Nursing initial assessment", "admission",
                     "nursing", sections=_NURSING_ASSESSMENT),
        DocumentType("ipd_nursing_note", "Nursing note", "admission", "nursing",
                     many=True, sections=_NURSING_NOTE),
        DocumentType("ipd_discharge_summary", "Discharge summary", "admission", "doctor",
                     sections=_DISCHARGE_SUMMARY),
        # Theatre notes belong to a surgery. The pre-op checklist is the
        # nurse's; the rest are the doctors'.
        DocumentType("ot_pre_op_checklist", "Pre-operative checklist", "surgery", "nursing",
                     sections=_PRE_OP_CHECKLIST),
        DocumentType("ot_pre_anaesthetic", "Pre-anaesthetic assessment", "surgery", "doctor",
                     sections=_PRE_ANAESTHETIC),
        DocumentType("ot_operation_note", "Operation note", "surgery", "doctor",
                     sections=_OPERATION_NOTE),
        DocumentType("ot_post_op_orders", "Post-operative orders", "surgery", "doctor",
                     sections=_POST_OP_ORDERS),
        # Day procedures. A clinic that scopes patients and sends them home the
        # same hour runs the same theatre, with a checklist that asks about an
        # escort rather than a marked site, and a report shaped like an
        # endoscopy rather than an operation.
        DocumentType("ot_day_procedure_checklist", "Day-procedure checklist", "surgery",
                     "nursing", sections=_DAY_PROCEDURE_CHECKLIST),
        DocumentType("ot_endoscopy_report", "Endoscopy report", "surgery", "doctor",
                     sections=_ENDOSCOPY_REPORT),
        # Certificates and consent forms. Doctors write and sign them; see
        # app/pads/forms.py for their wording and the checks before signing.
        DocumentType("cert_medical_leave", "Medical certificate", "patient", "doctor", many=True,
                     family="certificate", sections=forms.MEDICAL_LEAVE),
        DocumentType("cert_fitness", "Fitness certificate", "patient", "doctor", many=True,
                     family="certificate", sections=forms.FITNESS),
        DocumentType("cert_hospitalisation", "Hospitalisation certificate", "patient", "doctor",
                     many=True, family="certificate", requires="admission",
                     sections=forms.HOSPITALISATION),
        DocumentType("consent_general", "General consent for admission and treatment", "patient",
                     "doctor", many=True, family="consent", sections=forms.CONSENT_GENERAL),
        DocumentType("consent_surgical", "Informed consent for operation", "patient", "doctor",
                     many=True, family="consent", sections=forms.CONSENT_SURGICAL),
        DocumentType("consent_blood_transfusion", "Consent for blood transfusion", "patient",
                     "doctor", many=True, family="consent", sections=forms.CONSENT_BLOOD),
        DocumentType("consent_high_risk", "High-risk consent", "patient", "doctor", many=True,
                     family="consent", sections=forms.CONSENT_HIGH_RISK),
        DocumentType("lama_form", "Leaving against medical advice (LAMA)", "patient", "doctor",
                     many=True, family="consent", requires="admission", sections=forms.LAMA),
        # Written against an imaging order item when there is one; signing it
        # marks that item reported.
        DocumentType("radiology_report", "Radiology report", "patient", "doctor", many=True,
                     family="radiology", sections=forms.RADIOLOGY_REPORT),
    )
}

# Human names for each document type, kept as a plain mapping because the
# routes and the print filename only ever need the label.
DOCUMENT_TYPES: Dict[str, str] = {key: spec.label for key, spec in REGISTRY.items()}

#: Sections the system reads by key, so a layout may move and rename them but
#: not remove them or change what they hold. Signing a discharge summary sets
#: the admission's final diagnosis from `final_diagnosis`; an elective case
#: cannot go to theatre until the checklist's three checks are ticked.
PROTECTED_SECTIONS: Dict[str, Dict[str, List[str]]] = {
    "ipd_discharge_summary": {"final_diagnosis": []},
    "ot_pre_op_checklist": {"checks": ["identity_confirmed", "consent_signed", "site_marked"]},
    "ot_day_procedure_checklist": {
        "checks": ["identity_confirmed", "consent_signed", "fasting_confirmed"],
    },
    # Signing with the biopsy box ticked raises the histopathology order, so
    # the key may move on a layout but not disappear.
    "ot_endoscopy_report": {"specimen": ["biopsy_taken"]},
}


def document_type(key: str) -> Optional[DocumentType]:
    return REGISTRY.get(key)


def default_layout(document_type_key: str) -> Optional[List[Dict[str, Any]]]:
    """The built-in sections for a document type, or None if there is none."""
    spec = REGISTRY.get(document_type_key)
    if spec is None:
        return None
    # A fresh copy every time: a caller that mutates the result must not
    # change the default for every later request in this process.
    return [
        dict(section, fields=[dict(item) for item in section.get("fields", [])])
        for section in spec.sections
    ]
