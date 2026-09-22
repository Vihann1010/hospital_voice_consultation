"""The department registry — everything that differs between specialities.

Until now the code asked "is this orthopedics?" and treated anything else as
gynecology. That reads harmlessly and fails silently: a third department got
the gynaecology intake guide, was told it was seeing Dr Manisha Agarwal, and —
the serious one — screened against an empty red-flag list, so every emergency
utterance passed. Nothing raised. Nothing logged.

So department-specific content lives here, keyed by department, and is read
through :func:`profile_for`, which raises rather than guesses. A department
nobody has configured breaks at startup (see :func:`validate_department_config`,
called from the application lifespan), not in front of a patient.

Adding a department is therefore: a value on :class:`Department`, a migration
adding it to the Postgres enum, a :class:`DepartmentProfile` here, a red-flag
block in ``app.ai.emergency``, and a slot list in ``app.ai.session.memory``.
Miss any of them and the app will not boot.

The doctor's name is deliberately *not* here. It belongs to the consultant
register, which is where the hospital maintains it; see
``app.services.consultant_directory``.
"""
from dataclasses import dataclass
from typing import Dict, Mapping, Sequence, TypeVar

from app.models.enums import Department


class DepartmentNotConfigured(RuntimeError):
    """A department exists as an enum value but has no clinical content."""


@dataclass(frozen=True)
class DepartmentProfile:
    """Everything the platform needs to know to run one speciality."""

    # How the department is named on screens, prescriptions and reports.
    label: str
    # Three letters in prescription and visit numbers. Permanent once issued:
    # numbers already printed cannot be renumbered.
    code: str
    # Appended to the intake assistant's prompt — what to cover in the call.
    intake_guide: str
    # Prose for the risk model, describing what counts as a red flag here.
    # The deterministic regex screen is separate, in app.ai.emergency.
    red_flag_guide: str
    # Department-specific keys the extraction model should fill.
    extraction_fields: str
    # Two lines of Hindi self-care, used when the education model is
    # unavailable. Safe, generic, never a substitute for the consultation.
    fallback_self_care: Sequence[str]


_ORTHOPEDIC_GUIDE = """
Department-specific areas to cover naturally (Orthopedics):
- Exact location of the pain or problem (joint, bone, muscle, back region).
- Nature of pain: sharp, dull, throbbing, radiating; pain score 1-10.
- What makes it better or worse: rest, movement, position, time of day.
- Any injury, fall or accident that started it.
- Swelling, redness, warmth, stiffness, locking, clicking or giving-way.
- Morning stiffness and its duration; difficulty walking, climbing stairs, gripping.
- Numbness, tingling or weakness in limbs.
- Previous fractures, joint problems, physiotherapy, injections or implants.
- X-rays, MRI or other scans already done.
"""

_GYNECOLOGY_GUIDE = """
Department-specific areas to cover naturally (Gynecology):
- Menstrual history: last period date, cycle regularity, duration, flow, pain.
- Any chance of current pregnancy; obstetric history (pregnancies, deliveries, miscarriages) — ask gently.
- Unusual discharge, itching, burning, or pain during urination.
- Pelvic or lower abdominal pain and its relation to the cycle.
- Contraception currently used, if any.
- Menopause status where age-appropriate; any bleeding after menopause.
- Breast symptoms: lumps, pain, discharge.
- Previous gynecological procedures, surgeries or ultrasounds.
Be especially respectful and unhurried with these questions.
"""

# Drafted for the gastroenterology clinic and NOT yet reviewed by a
# gastroenterologist. It is deliberately conservative — it asks, it never
# advises — but it must be signed off before it is used on real patients.
_GASTROENTEROLOGY_GUIDE = """
Department-specific areas to cover naturally (Gastroenterology):
- Exact site of the abdominal pain or discomfort, and whether it moves or radiates.
- Relation to food: before or after eating, which foods, how long after; night pain.
- Heartburn, acid reflux, sour regurgitation, difficulty or pain on swallowing.
- Nausea and vomiting — how often, and whether there was ever blood in it.
- Bowel habit: how many times a day or week, any recent change, straining, urgency.
- Stool appearance: loose, hard, black and tarry, blood or mucus, pale or greasy.
- Appetite and weight — any unintended weight loss, and over how long.
- Bloating, excess gas, early fullness after small meals.
- Jaundice: yellow eyes or skin, dark urine, itching.
- Alcohol intake, smoking, and regular painkillers (especially NSAIDs).
- Past endoscopy, colonoscopy, ultrasound or liver tests, and any known liver
  or gallbladder disease; family history of bowel or stomach cancer.
Ask about stool, bleeding and alcohol matter-of-factly and without embarrassment.
"""

_DENTISTRY_GUIDE = """
Department-specific areas to cover naturally (Dentistry):
- Which tooth or area hurts: upper or lower jaw, left or right, front or back;
  whether they can point to one tooth or the pain is spread out.
- What brings the pain on: hot, cold or sweet things, biting or chewing; how
  long it lasts after the trigger goes away; whether it wakes them at night.
- Swelling of the gum, cheek, face or jaw, and whether it is getting bigger;
  any pus or bad taste; fever.
- Bleeding gums when brushing, loose teeth, bad breath.
- Any injury to the mouth or face, a broken or knocked-out tooth.
- Difficulty opening the mouth, chewing or swallowing.
- Last dental visit and treatment: fillings, root canals, extractions, crowns,
  braces, dentures, implants.
- Brushing habit, tobacco, gutkha, paan or smoking.
- Blood thinners, diabetes and heart conditions: these change what can be
  done in the chair, so ask for them plainly.
Keep it short and practical; the dentist will examine the mouth.
"""


_PROFILES: Dict[Department, DepartmentProfile] = {
    Department.ORTHOPEDICS: DepartmentProfile(
        label="Orthopedics",
        code="ORT",
        intake_guide=_ORTHOPEDIC_GUIDE,
        red_flag_guide=(
            "Orthopedic red flags include: suspected open/deformed fracture, neurovascular "
            "compromise (numb/cold/pulseless limb), cauda equina features (saddle anaesthesia, "
            "urinary retention/incontinence with back pain), septic arthritis features (hot "
            "swollen joint + fever), night pain with weight loss or cancer history, significant "
            "trauma in the elderly, progressive neurological deficit."
        ),
        extraction_fields="affected_joint, injury_history, imaging_done",
        fallback_self_care=(
            "दर्द वाले अंग को आराम दें और उसे अनावश्यक दबाव या चोट से बचाएं।",
            "अपनी सभी जांच रिपोर्ट साथ लाएं और डॉक्टर की सलाह के बिना दवा शुरू या बंद न करें।",
        ),
    ),
    Department.GYNECOLOGY: DepartmentProfile(
        label="Gynecology",
        code="GYN",
        intake_guide=_GYNECOLOGY_GUIDE,
        red_flag_guide=(
            "Gynecological red flags include: pregnancy with bleeding or severe abdominal pain "
            "(possible ectopic/miscarriage), reduced fetal movements, heavy bleeding with "
            "dizziness/syncope, postmenopausal bleeding, fever with pelvic pain and discharge "
            "(possible PID/sepsis), severe hyperemesis with dehydration."
        ),
        extraction_fields="menstrual_history, pregnancy_status, obstetric_history",
        fallback_self_care=(
            "आराम करें, पर्याप्त पानी पिएं और अपनी जांच रिपोर्ट तथा दवाओं की सूची साथ लाएं।",
            "तेज दर्द, अधिक रक्तस्राव, चक्कर या सांस लेने में परेशानी हो तो तुरंत अस्पताल जाएं।",
        ),
    ),
    Department.GASTROENTEROLOGY: DepartmentProfile(
        label="Gastroenterology",
        code="GAS",
        intake_guide=_GASTROENTEROLOGY_GUIDE,
        red_flag_guide=(
            "Gastroenterological red flags include: haematemesis or coffee-ground vomit, "
            "melaena or fresh rectal bleeding, progressive dysphagia or odynophagia, "
            "unintentional weight loss with abdominal pain, persistent vomiting with "
            "abdominal distension and absolute constipation (possible obstruction), new "
            "jaundice, severe epigastric pain radiating to the back (possible pancreatitis), "
            "fever with right upper quadrant pain (possible cholangitis), and any change in "
            "bowel habit over the age of fifty."
        ),
        extraction_fields=(
            "pain_site, relation_to_food, bowel_habit_change, stool_appearance, "
            "bleeding_history, endoscopy_history"
        ),
        fallback_self_care=(
            "हल्का और सादा भोजन लें, पर्याप्त पानी पिएं, और डॉक्टर की सलाह के बिना दर्द "
            "निवारक दवा न लें।",
            "उल्टी या शौच में खून आए, पेट में तेज दर्द हो, या आंखें पीली पड़ें तो तुरंत "
            "अस्पताल जाएं।",
        ),
    ),
    Department.DENTISTRY: DepartmentProfile(
        label="Dentistry",
        code="DEN",
        intake_guide=_DENTISTRY_GUIDE,
        red_flag_guide=(
            "Dental red flags include: facial or neck swelling that is spreading, closing "
            "an eye, or raising the floor of the mouth (possible space infection or "
            "Ludwig's angina — an airway emergency), difficulty swallowing or breathing "
            "with a dental infection, inability to open the mouth with fever, bleeding "
            "after an extraction that does not stop with pressure, a knocked-out "
            "permanent tooth (replant within the hour), and a suspected jaw fracture "
            "after injury (teeth no longer meet, jaw deformed or numb)."
        ),
        extraction_fields=(
            "tooth_or_area, pain_triggers, swelling, gum_bleeding, "
            "dental_history, tobacco_use"
        ),
        fallback_self_care=(
            "गुनगुने नमक वाले पानी से कुल्ला करें, और दर्द वाली तरफ से न चबाएं।",
            "चेहरे या गले में सूजन बढ़े, मुंह न खुले, बुखार हो, या निगलने या सांस लेने में "
            "परेशानी हो तो तुरंत अस्पताल जाएं।",
        ),
    ),
}


V = TypeVar("V")


def require_department(table: Mapping[Department, V], department: Department, what: str) -> V:
    """Read a per-department table, raising when the department is missing.

    Every department-keyed lookup in the codebase goes through this rather than
    ``.get(department, <something for another speciality>)``. The default is
    what turned a missing configuration into a patient-facing mistake.
    """
    try:
        return table[department]
    except KeyError:
        raise DepartmentNotConfigured(
            f"No {what} is configured for department '{department.value}'. "
            f"Configure it in app/departments.py and the module that owns {what}."
        ) from None


def profile_for(department: Department) -> DepartmentProfile:
    return require_department(_PROFILES, department, "department profile")


def label_for(department: Department) -> str:
    return profile_for(department).label


def code_for(department: Department) -> str:
    return profile_for(department).code


def validate_department_config() -> None:
    """Refuse to serve a department that is only half-configured.

    Called from the application lifespan, before the node is marked ready. The
    imports are local because the tables being checked import this module.
    """
    from app.ai.emergency import DEPARTMENT_FLAGS
    from app.ai.session.memory import DEPARTMENT_SLOTS

    tables = {
        "department profile": _PROFILES,
        "emergency red flags": DEPARTMENT_FLAGS,
        "intake slot checklist": DEPARTMENT_SLOTS,
    }
    missing = [
        f"{department.value}: no {what}"
        for department in Department
        for what, table in tables.items()
        if department not in table
    ]
    if missing:
        raise DepartmentNotConfigured(
            "Some departments are configured only partly, which would fail "
            "silently at consultation time:\n  " + "\n  ".join(missing)
        )
