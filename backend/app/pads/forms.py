"""Certificates and consent forms: their fields, their wording, their checks.

Both are Visit Pad documents, so they are written, signed, corrected and
printed like every other clinical document. Three things set them apart:

* **The wording is fixed.** What a certificate certifies, and what a patient
  agrees to on a consent form, is composed from the fields at print time
  rather than typed free-hand, so the sentence on paper always matches the
  dates and diagnosis recorded in the system.
* **They are numbered.** A certificate or consent form is quoted back to the
  hospital by employers, insurers and courts, so each gets a serial number
  when it is first signed (MC26-00001, CN26-00001). A corrected version keeps
  the number of the document it corrects.
* **They are checked before signing.** A rest period that ends before it
  starts, an examination dated tomorrow, a hospitalisation certificate whose
  dates differ from the admission, a minor "consenting" for themselves, a
  guardian with no stated relation — each is refused with the reason.

The consent wording is printed in English and Hindi. It was drafted for this
system and should be reviewed by the hospital's medico-legal adviser before
the forms replace the printed ones in use.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from app.theatre.rules import ANAESTHESIA_TYPES, LATERALITY

SERIAL_PREFIX: Dict[str, str] = {"certificate": "MC", "consent": "CN", "radiology": "RR"}

#: Investigation categories a radiology report is written for.
IMAGING_CATEGORIES = {"xray", "mri", "ct", "ultrasound", "dexa"}

GUARDIAN = "Guardian / relative"
CONSENT_BY = ["Patient", GUARDIAN]
RELATIONS = [
    "Father", "Mother", "Husband", "Wife", "Son", "Daughter", "Brother", "Sister",
    "Other relative", "Legal guardian",
]
CANNOT_CONSENT = [
    "Minor (under 18)",
    "Unconscious",
    "Not mentally competent to decide",
    "Too unwell to sign",
    "Patient asked a relative to decide",
]
LANGUAGES = ["Hindi", "English", "Other"]
FIT_FOR = [
    "Resume duty",
    "Resume school / college",
    "Travel",
    "Physical activity and sports",
    "Other",
]
BLOOD_COMPONENTS = [
    "Whole blood", "Packed red cells", "Fresh frozen plasma", "Platelets", "Cryoprecipitate",
]
ADULT_AGE = 18


def _consent_by() -> Dict[str, Any]:
    return {
        "key": "consent_by",
        "title": "Who consented",
        "kind": "fields",
        "fields": [
            {"key": "consent_given_by", "label": "Consent given by", "type": "select",
             "options": CONSENT_BY, "required": True},
            {"key": "guardian_name", "label": "Guardian's name", "type": "text"},
            {"key": "guardian_relation", "label": "Relation to patient", "type": "select",
             "options": RELATIONS},
            {"key": "reason_cannot_consent", "label": "Why the patient is not consenting",
             "type": "select", "options": CANNOT_CONSENT},
            {"key": "language", "label": "Explained in", "type": "select", "options": LANGUAGES,
             "required": True},
            {"key": "language_other", "label": "Other language", "type": "text"},
            {"key": "witness_name", "label": "Witness's name", "type": "text", "required": True},
            {"key": "witness_relation", "label": "Witness — relation or staff role", "type": "text"},
            {"key": "interpreter_name", "label": "Interpreter, if any", "type": "text"},
        ],
    }


# --------------------------------------------------------------- certificates
MEDICAL_LEAVE: List[Dict[str, Any]] = [
    {
        "key": "certificate",
        "title": "Certificate",
        "kind": "fields",
        "fields": [
            {"key": "examined_on", "label": "Examined on", "type": "date", "required": True},
            {"key": "diagnosis", "label": "Diagnosis / condition", "type": "text", "required": True},
            {"key": "rest_from", "label": "Rest advised from", "type": "date", "required": True},
            {"key": "rest_to", "label": "Rest advised to", "type": "date", "required": True},
            {"key": "advice", "label": "Advice", "type": "textarea"},
            {"key": "submitted_to", "label": "For submission to", "type": "text"},
        ],
    },
]

FITNESS: List[Dict[str, Any]] = [
    {
        "key": "certificate",
        "title": "Certificate",
        "kind": "fields",
        "fields": [
            {"key": "examined_on", "label": "Examined on", "type": "date", "required": True},
            {"key": "condition", "label": "Treated for", "type": "text", "required": True},
            {"key": "fit_for", "label": "Fit to", "type": "select", "options": FIT_FOR,
             "required": True},
            {"key": "fit_for_other", "label": "Fit to (other)", "type": "text"},
            {"key": "fit_from", "label": "Fit from", "type": "date", "required": True},
            {"key": "restrictions", "label": "Restrictions", "type": "textarea"},
            {"key": "submitted_to", "label": "For submission to", "type": "text"},
        ],
    },
]

HOSPITALISATION: List[Dict[str, Any]] = [
    {
        "key": "certificate",
        "title": "Certificate",
        "kind": "fields",
        "fields": [
            {"key": "admitted_on", "label": "Admitted on", "type": "date", "required": True},
            {"key": "discharged_on", "label": "Discharged on", "type": "date"},
            {"key": "diagnosis", "label": "Diagnosis", "type": "text", "required": True},
            {"key": "procedures", "label": "Procedures performed", "type": "textarea"},
            {"key": "submitted_to", "label": "For submission to", "type": "text"},
        ],
    },
]

# ------------------------------------------------------------------ consents
CONSENT_GENERAL: List[Dict[str, Any]] = [
    _consent_by(),
    {"key": "notes", "title": "Notes", "kind": "text"},
]

CONSENT_SURGICAL: List[Dict[str, Any]] = [
    {
        "key": "details",
        "title": "Operation",
        "kind": "fields",
        "fields": [
            {"key": "procedure", "label": "Operation / procedure", "type": "text", "required": True},
            {"key": "side", "label": "Side", "type": "select", "options": LATERALITY, "required": True},
            {"key": "diagnosis", "label": "Diagnosis", "type": "text", "required": True},
            {"key": "surgeon_name", "label": "Surgeon", "type": "text", "required": True},
            {"key": "anaesthesia_type", "label": "Anaesthesia", "type": "select",
             "options": ANAESTHESIA_TYPES, "required": True},
        ],
    },
    {"key": "risks", "title": "Specific risks explained", "kind": "list",
     "catalogue_category": "consent_risk", "placeholder": "Bleeding, infection, stiffness…"},
    {"key": "alternatives", "title": "Alternatives explained", "kind": "text"},
    {
        "key": "permissions",
        "title": "The patient also agrees that",
        "kind": "fields",
        "fields": [
            {"key": "additional_procedure", "type": "checkbox",
             "label": "Additional procedure if needed to save life or prevent serious harm"},
            {"key": "blood_transfusion", "type": "checkbox",
             "label": "Blood may be transfused if needed"},
            {"key": "tissue_examination", "type": "checkbox",
             "label": "Removed tissue may be sent for examination and then disposed of"},
            {"key": "photographs", "type": "checkbox",
             "label": "Clinical photographs may be taken for the medical record"},
        ],
    },
    _consent_by(),
]

CONSENT_BLOOD: List[Dict[str, Any]] = [
    {
        "key": "details",
        "title": "Transfusion",
        "kind": "fields",
        "fields": [
            {"key": "indication", "label": "Reason for transfusion", "type": "text", "required": True},
            {"key": "components", "label": "Blood / components", "type": "multiselect",
             "options": BLOOD_COMPONENTS, "required": True},
        ],
    },
    {"key": "alternatives", "title": "Alternatives explained", "kind": "text"},
    _consent_by(),
]

CONSENT_HIGH_RISK: List[Dict[str, Any]] = [
    {
        "key": "details",
        "title": "Treatment",
        "kind": "fields",
        "fields": [
            {"key": "condition", "label": "Patient's condition", "type": "textarea", "required": True},
            {"key": "treatment", "label": "Treatment / procedure", "type": "text", "required": True},
        ],
    },
    {"key": "risks", "title": "Specific risks explained", "kind": "list",
     "catalogue_category": "consent_risk", "placeholder": "Risk of death, ventilator support…"},
    {"key": "alternatives", "title": "Alternatives explained", "kind": "text"},
    _consent_by(),
]

LAMA: List[Dict[str, Any]] = [
    {
        "key": "details",
        "title": "Leaving against medical advice",
        "kind": "fields",
        "fields": [
            {"key": "advice", "label": "Treatment the doctors advised", "type": "textarea",
             "required": True},
            {"key": "risks_explained", "label": "Risks of leaving now, as explained", "type": "textarea",
             "required": True},
            {"key": "reason", "label": "Reason given for leaving", "type": "text"},
        ],
    },
    _consent_by(),
]

RADIOLOGY_REPORT: List[Dict[str, Any]] = [
    {
        "key": "study",
        "title": "Study",
        "kind": "fields",
        "fields": [
            {"key": "study_name", "label": "Study", "type": "text", "required": True},
            {"key": "site", "label": "Region / side", "type": "text"},
            {"key": "study_date", "label": "Study date", "type": "date", "required": True},
            {"key": "indication", "label": "Clinical indication", "type": "text"},
            {"key": "comparison", "label": "Compared with", "type": "text"},
        ],
    },
    {"key": "technique", "title": "Technique", "kind": "text"},
    {"key": "findings", "title": "Findings", "kind": "text"},
    {"key": "impression", "title": "Impression", "kind": "list",
     "catalogue_category": "radiology_impression", "placeholder": "One conclusion per line"},
    {"key": "recommendation", "title": "Recommendation", "kind": "text"},
]

TITLE_HI: Dict[str, str] = {
    "consent_general": "भर्ती एवं उपचार हेतु सामान्य सहमति पत्र",
    "consent_surgical": "ऑपरेशन हेतु सूचित सहमति पत्र",
    "consent_blood_transfusion": "रक्त चढ़ाने हेतु सहमति पत्र",
    "consent_high_risk": "उच्च जोखिम सहमति पत्र",
    "lama_form": "चिकित्सीय सलाह के विरुद्ध अस्पताल छोड़ने का घोषणा पत्र",
}

STATEMENTS: Dict[str, Dict[str, List[str]]] = {
    "consent_general": {
        "en": [
            "I consent to admission to this hospital and to the examination, investigations and "
            "treatment that the treating doctors consider necessary.",
            "The nature of the illness, the proposed treatment, its expected benefits and its common "
            "risks have been explained to me in a language I understand, and I have been able to ask questions.",
            "I understand that no guarantee has been given about the outcome of treatment.",
            "I agree to follow the hospital's rules and to pay its charges as per the hospital's tariff.",
            "I understand that I may withdraw this consent at any time, and that the consequences of "
            "doing so will be explained to me.",
        ],
        "hi": [
            "मैं इस अस्पताल में भर्ती होने तथा इलाज करने वाले डॉक्टरों द्वारा आवश्यक समझी गई जाँच और उपचार के लिए सहमति देता/देती हूँ।",
            "बीमारी, प्रस्तावित उपचार, उसके अपेक्षित लाभ और सामान्य जोखिम मुझे मेरी समझ की भाषा में समझा दिए गए हैं, और मुझे प्रश्न पूछने का अवसर दिया गया है।",
            "मैं समझता/समझती हूँ कि उपचार के परिणाम के बारे में कोई गारंटी नहीं दी गई है।",
            "मैं अस्पताल के नियमों का पालन करने और अस्पताल की दर-सूची के अनुसार शुल्क का भुगतान करने के लिए सहमत हूँ।",
            "मैं समझता/समझती हूँ कि मैं यह सहमति कभी भी वापस ले सकता/सकती हूँ, और ऐसा करने के परिणाम मुझे समझाए जाएँगे।",
        ],
    },
    "consent_surgical": {
        "en": [
            "I consent to the operation named above, on the side stated, to be performed by the surgeon "
            "named or by a team under the surgeon's supervision.",
            "What the operation is, why it is advised, its expected benefits, its risks — including the "
            "specific risks listed above — and the alternatives, including not operating, have been "
            "explained to me in a language I understand. I have been able to ask questions and they have "
            "been answered.",
            "I consent to the anaesthesia stated above. Its risks have been explained to me.",
            "I understand that no guarantee has been given about the result of the operation.",
        ],
        "hi": [
            "मैं ऊपर लिखे ऑपरेशन के लिए, बताई गई तरफ़ पर, नामित सर्जन या सर्जन की देखरेख में टीम द्वारा किए जाने की सहमति देता/देती हूँ।",
            "ऑपरेशन क्या है, इसकी सलाह क्यों दी गई है, इसके अपेक्षित लाभ, इसके जोखिम — ऊपर लिखे विशेष जोखिमों सहित — और इसके विकल्प, ऑपरेशन न कराने सहित, मुझे मेरी समझ की भाषा में समझा दिए गए हैं। मुझे प्रश्न पूछने का अवसर मिला और उनके उत्तर दिए गए।",
            "मैं ऊपर बताए गए एनेस्थीसिया (बेहोशी या सुन्न करने) के लिए सहमति देता/देती हूँ। इसके जोखिम मुझे समझा दिए गए हैं।",
            "मैं समझता/समझती हूँ कि ऑपरेशन के परिणाम के बारे में कोई गारंटी नहीं दी गई है।",
        ],
    },
    "consent_blood_transfusion": {
        "en": [
            "I consent to the transfusion of the blood or blood components stated above.",
            "The reason for the transfusion, its risks — including allergic and fever reactions, fluid "
            "overload and, rarely, infection despite testing — and the alternatives have been explained "
            "to me in a language I understand.",
            "I understand that the blood supplied has been tested as the law requires, but that no test "
            "removes every risk.",
        ],
        "hi": [
            "मैं ऊपर लिखे रक्त या रक्त घटकों को चढ़ाए जाने की सहमति देता/देती हूँ।",
            "रक्त चढ़ाने का कारण, इसके जोखिम — एलर्जी और बुखार की प्रतिक्रिया, शरीर में तरल की अधिकता, और जाँच के बावजूद कभी-कभी संक्रमण — तथा इसके विकल्प मुझे मेरी समझ की भाषा में समझा दिए गए हैं।",
            "मैं समझता/समझती हूँ कि दिया जाने वाला रक्त क़ानून के अनुसार जाँचा गया है, परंतु कोई भी जाँच हर जोखिम को समाप्त नहीं करती।",
        ],
    },
    "consent_high_risk": {
        "en": [
            "It has been explained to me, in a language I understand, that the patient's condition stated "
            "above is serious and that the treatment stated above carries a higher than usual risk, "
            "including the risk of disability or death.",
            "The specific risks listed above and the alternatives have been explained to me, and I have "
            "been able to ask questions.",
            "Understanding these risks, I consent to the treatment stated above.",
        ],
        "hi": [
            "मुझे मेरी समझ की भाषा में समझा दिया गया है कि ऊपर लिखी मरीज़ की स्थिति गंभीर है और ऊपर लिखे उपचार में सामान्य से अधिक जोखिम है, जिसमें विकलांगता या मृत्यु का जोखिम भी शामिल है।",
            "ऊपर लिखे विशेष जोखिम और विकल्प मुझे समझा दिए गए हैं, और मुझे प्रश्न पूछने का अवसर मिला है।",
            "इन जोखिमों को समझते हुए मैं ऊपर लिखे उपचार के लिए सहमति देता/देती हूँ।",
        ],
    },
    "lama_form": {
        "en": [
            "I am taking the patient away from the hospital against the advice of the treating doctors.",
            "The doctors' advice, and the risks of leaving now — including worsening of the condition, "
            "disability or death — have been explained to me in a language I understand.",
            "I take full responsibility for this decision and its consequences, and I will not hold the "
            "hospital or its staff responsible for them.",
            "I have been told that the patient may return to this hospital, or go to another hospital, at any time.",
        ],
        "hi": [
            "मैं इलाज करने वाले डॉक्टरों की सलाह के विरुद्ध मरीज़ को अस्पताल से ले जा रहा/रही हूँ।",
            "डॉक्टरों की सलाह, और अभी जाने के जोखिम — स्थिति बिगड़ना, विकलांगता या मृत्यु सहित — मुझे मेरी समझ की भाषा में समझा दिए गए हैं।",
            "मैं इस निर्णय और इसके परिणामों की पूरी ज़िम्मेदारी लेता/लेती हूँ, और इनके लिए अस्पताल या उसके कर्मचारियों को ज़िम्मेदार नहीं ठहराऊँगा/ठहराऊँगी।",
            "मुझे बताया गया है कि मरीज़ कभी भी इस अस्पताल में वापस आ सकता/सकती है, या किसी अन्य अस्पताल में जा सकता/सकती है।",
        ],
    },
}

SIGNATURE_LABELS = {
    "patient": ("Signature or thumb impression of patient / guardian",
                "मरीज़ / अभिभावक के हस्ताक्षर या अँगूठे का निशान"),
    "witness": ("Signature of witness", "गवाह के हस्ताक्षर"),
    "name": ("Name", "नाम"),
    "when": ("Date and time", "दिनांक व समय"),
}


# ------------------------------------------------------------------- helpers
def fields(values: Dict[str, Any], section: str) -> Dict[str, Any]:
    return ((values or {}).get(section) or {}).get("fields") or {}


def _items(values: Dict[str, Any], section: str) -> List[str]:
    return [item for item in ((values or {}).get(section) or {}).get("items") or [] if str(item).strip()]


def _text(values: Dict[str, Any], section: str) -> str:
    return str(((values or {}).get(section) or {}).get("text") or "").strip()


def as_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def show_date(value: Any) -> str:
    moment = as_date(value)
    return moment.strftime("%d %b %Y") if moment else "—"


# ------------------------------------------------------------------- prefill
def prefill(
    document_type: str,
    *,
    today: date,
    admission: Optional[Dict[str, Any]] = None,
    surgery: Optional[Dict[str, Any]] = None,
    order_item: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """What a new certificate or consent form starts with.

    Only facts the hospital already holds: today's date where the form is
    written on the day, the admission's own dates and diagnosis, the theatre
    booking's operation and side. Who is consenting and in what language is
    never pre-selected — a default there is an answer nobody gave.
    """
    iso = today.isoformat()
    if document_type == "radiology_report":
        found = {"study_date": iso}
        if order_item:
            found.update({
                "study_name": order_item.get("name") or "",
                "site": order_item.get("site") or "",
                "indication": order_item.get("indication") or "",
            })
        return {"study": {"fields": found}}
    if document_type == "cert_medical_leave":
        return {"certificate": {"fields": {"examined_on": iso, "rest_from": iso}}}
    if document_type == "cert_fitness":
        return {"certificate": {"fields": {"examined_on": iso, "fit_from": iso}}}
    if document_type == "cert_hospitalisation" and admission:
        found = {
            "admitted_on": admission["admitted_on"].isoformat(),
            "diagnosis": admission.get("diagnosis") or "",
        }
        if admission.get("discharged_on"):
            found["discharged_on"] = admission["discharged_on"].isoformat()
        return {"certificate": {"fields": found}}
    if document_type == "consent_surgical" and surgery:
        return {"details": {"fields": {
            "procedure": surgery.get("procedure") or "",
            "side": surgery.get("side") or "",
            "diagnosis": surgery.get("diagnosis") or "",
            "surgeon_name": surgery.get("surgeon") or "",
            "anaesthesia_type": surgery.get("anaesthesia") or "",
        }}}
    return {}


# --------------------------------------------------------------------- check
def _check_consent_by(values: Dict[str, Any], patient_age: Optional[int]) -> List[str]:
    given = fields(values, "consent_by")
    problems: List[str] = []
    by_guardian = given.get("consent_given_by") == GUARDIAN
    if given.get("consent_given_by") == "Patient" and patient_age is not None and patient_age < ADULT_AGE:
        problems.append(
            f"The patient is {patient_age} — under {ADULT_AGE}, so a parent or guardian must give consent"
        )
    if by_guardian:
        if not str(given.get("guardian_name") or "").strip():
            problems.append("Give the guardian's name")
        if not given.get("guardian_relation"):
            problems.append("Give the guardian's relation to the patient")
        if not given.get("reason_cannot_consent"):
            problems.append("Say why the patient is not consenting personally")
    if given.get("language") == "Other" and not str(given.get("language_other") or "").strip():
        problems.append("Name the language the form was explained in")
    return problems


def check(
    document_type: str,
    values: Dict[str, Any],
    *,
    today: date,
    patient_age: Optional[int] = None,
    admission: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Why this certificate or consent form cannot be signed yet. Empty when it can.

    Required fields are checked by the pad itself; these are the rules
    between fields, and against the hospital's own record.
    """
    problems: List[str] = []
    cert = fields(values, "certificate")

    if document_type == "cert_medical_leave":
        examined, start, end = (as_date(cert.get(k)) for k in ("examined_on", "rest_from", "rest_to"))
        if examined and examined > today:
            problems.append("The examination date is in the future")
        if start and end and end < start:
            problems.append("Rest cannot end before it starts")
        if examined and start and start < examined:
            problems.append(
                "Rest cannot be certified from before the patient was examined — the certificate "
                "would cover days the doctor did not see"
            )

    elif document_type == "cert_fitness":
        examined, start = as_date(cert.get("examined_on")), as_date(cert.get("fit_from"))
        if examined and examined > today:
            problems.append("The examination date is in the future")
        if examined and start and start < examined:
            problems.append("Fitness cannot be certified from before the examination")
        if cert.get("fit_for") == "Other" and not str(cert.get("fit_for_other") or "").strip():
            problems.append("Say what the patient is fit for")

    elif document_type == "cert_hospitalisation":
        if admission is None:
            problems.append("A hospitalisation certificate must be issued from the admission")
        else:
            admitted = as_date(cert.get("admitted_on"))
            discharged = as_date(cert.get("discharged_on"))
            if admitted != admission["admitted_on"]:
                problems.append(
                    f"The admission date must match the admission record ({show_date(admission['admitted_on'])})"
                )
            if admission.get("discharged_on") is None:
                if discharged is not None:
                    problems.append("The patient has not been discharged — leave the discharge date empty")
            elif discharged != admission["discharged_on"]:
                problems.append(
                    f"The discharge date must match the admission record ({show_date(admission['discharged_on'])})"
                )

    elif document_type == "consent_surgical":
        if not _items(values, "risks"):
            problems.append("List the specific risks that were explained")
        if not _text(values, "alternatives"):
            problems.append("Record the alternatives that were explained")
        problems += _check_consent_by(values, patient_age)

    elif document_type == "consent_high_risk":
        if not _items(values, "risks"):
            problems.append("List the specific risks that were explained")
        problems += _check_consent_by(values, patient_age)

    elif document_type == "radiology_report":
        taken = as_date(fields(values, "study").get("study_date"))
        if taken and taken > today:
            problems.append("The study date is in the future")
        if not _text(values, "findings"):
            problems.append("Write the findings")
        if not _items(values, "impression"):
            problems.append("Give an impression")

    elif document_type in ("consent_general", "consent_blood_transfusion", "lama_form"):
        problems += _check_consent_by(values, patient_age)

    return problems


# ----------------------------------------------------------------- wording
def _who(patient: Any) -> str:
    gender = getattr(getattr(patient, "gender", None), "value", getattr(patient, "gender", "")) or ""
    name = " ".join(part for part in (getattr(patient, "title", None), patient.name) if part)
    guardian = ""
    if getattr(patient, "guardian_name", None):
        relation = getattr(patient, "guardian_relation", None) or "relative of"
        guardian = f", {relation} {patient.guardian_name}"
    return (
        f"{name}{guardian}, aged {patient.age} years, {str(gender).title()}, "
        f"UHID {getattr(patient, 'uhid', None) or '—'}"
    )


def _purpose(cert: Dict[str, Any]) -> str:
    choice = cert.get("fit_for")
    return {
        "Resume duty": "resume duty",
        "Resume school / college": "resume school or college",
        "Travel": "travel",
        "Physical activity and sports": "take part in physical activity and sports",
    }.get(choice, str(cert.get("fit_for_other") or "").strip() or "resume normal activity")


def certificate_paragraphs(
    document_type: str,
    values: Dict[str, Any],
    *,
    patient: Any,
    issued_on: date,
    ip_number: Optional[str] = None,
) -> List[str]:
    """The certificate's wording, composed from its fields."""
    cert = fields(values, "certificate")
    who = _who(patient)
    lines: List[str] = []

    if document_type == "cert_medical_leave":
        start, end = as_date(cert.get("rest_from")), as_date(cert.get("rest_to"))
        days = (end - start).days + 1 if start and end else None
        span = f" — {days} day{'s' if days != 1 else ''}" if days else ""
        lines.append(
            f"This is to certify that {who}, was examined by me on {show_date(cert.get('examined_on'))}. "
            f"The patient is suffering from {cert.get('diagnosis') or '—'} and has been advised rest from "
            f"{show_date(start)} to {show_date(end)}, both days inclusive{span}."
        )
        if str(cert.get("advice") or "").strip():
            lines.append(f"Advice: {cert['advice'].strip()}")

    elif document_type == "cert_fitness":
        lines.append(
            f"This is to certify that {who}, was under my care for {cert.get('condition') or '—'} and was "
            f"examined by me on {show_date(cert.get('examined_on'))}. In my opinion the patient is fit to "
            f"{_purpose(cert)} from {show_date(cert.get('fit_from'))}."
        )
        if str(cert.get("restrictions") or "").strip():
            lines.append(f"Restrictions: {cert['restrictions'].strip()}")

    elif document_type == "cert_hospitalisation":
        stay = f"was admitted to this hospital on {show_date(cert.get('admitted_on'))}"
        if ip_number:
            stay += f" under IP number {ip_number}"
        if cert.get("discharged_on"):
            stay += f" and was discharged on {show_date(cert.get('discharged_on'))}"
        else:
            stay += f" and remains admitted as of {show_date(issued_on)}"
        lines.append(f"This is to certify that {who}, {stay}, for {cert.get('diagnosis') or '—'}.")
        if str(cert.get("procedures") or "").strip():
            lines.append(f"Procedures performed: {cert['procedures'].strip()}")

    if str(cert.get("submitted_to") or "").strip():
        lines.append(f"Issued at the patient's request for submission to {cert['submitted_to'].strip()}.")
    return lines


def guardian_clause(values: Dict[str, Any]) -> Optional[str]:
    given = fields(values, "consent_by")
    if given.get("consent_given_by") != GUARDIAN:
        return None
    return (
        f"Consent given on the patient's behalf by {given.get('guardian_name') or '—'} "
        f"({given.get('guardian_relation') or 'relation not stated'}), because: "
        f"{given.get('reason_cannot_consent') or 'reason not stated'}."
    )
