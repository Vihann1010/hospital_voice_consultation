"""Prescribing formulary: medicines, dosing defaults and interaction pairs.

Held in code for the same reasons as the investigation catalog — it is
reference data that ships with releases and must be searchable without a query.
Prescriptions denormalise the drug name at issue time, so revising this file
never alters a prescription already printed.

Ingredient resolution deliberately reuses `app.ai.pipeline.medication_rules`,
so the duplicate and allergy logic proven in the copilot is the same logic that
guards prescribing. This module adds the prescribing-specific parts: dose
forms, strengths, default frequencies and a deterministic interaction table.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from app.ai.pipeline.medication_rules import DRUG_CLASSES, ingredients_of, normalize_name
from app.models.enums import Department


@dataclass(frozen=True)
class Medicine:
    code: str
    name: str                      # brand or common name as prescribed
    ingredients: List[str]
    form: str                      # Tablet | Capsule | Syrup | Injection | Ointment | Sachet
    strengths: List[str] = field(default_factory=list)
    default_frequency: Optional[str] = None
    default_duration: Optional[str] = None
    default_timing: Optional[str] = None
    category: str = "General"
    departments: List[Department] = field(default_factory=list)
    note: Optional[str] = None


M = Medicine

FORMULARY: List[Medicine] = [
    # ---------------------------- Analgesics / NSAIDs ----------------------
    M("PARA", "Paracetamol", ["paracetamol"], "Tablet", ["500 mg", "650 mg"], "SOS", "3 days",
      "after food", "Analgesic / Antipyretic"),
    M("DOLO", "Dolo", ["paracetamol"], "Tablet", ["650 mg"], "SOS", "3 days", "after food",
      "Analgesic / Antipyretic"),
    M("CROCIN", "Crocin", ["paracetamol"], "Tablet", ["500 mg", "650 mg"], "SOS", "3 days",
      "after food", "Analgesic / Antipyretic"),
    M("COMBIFLAM", "Combiflam", ["ibuprofen", "paracetamol"], "Tablet", ["400/325 mg"], "BD",
      "3 days", "after food", "Analgesic / NSAID"),
    M("BRUFEN", "Brufen", ["ibuprofen"], "Tablet", ["200 mg", "400 mg", "600 mg"], "TDS", "5 days",
      "after food", "NSAID"),
    M("ZERODOL", "Zerodol", ["aceclofenac"], "Tablet", ["100 mg"], "BD", "5 days", "after food",
      "NSAID", [Department.ORTHOPEDICS]),
    M("ZERODOL_SP", "Zerodol SP", ["aceclofenac", "paracetamol", "serratiopeptidase"], "Tablet",
      ["100/325/15 mg"], "BD", "5 days", "after food", "NSAID", [Department.ORTHOPEDICS]),
    M("HIFENAC", "Hifenac", ["aceclofenac"], "Tablet", ["100 mg"], "BD", "5 days", "after food",
      "NSAID", [Department.ORTHOPEDICS]),
    M("VOVERAN", "Voveran", ["diclofenac"], "Tablet", ["50 mg"], "BD", "5 days", "after food",
      "NSAID", [Department.ORTHOPEDICS]),
    M("NAPROSYN", "Naprosyn", ["naproxen"], "Tablet", ["250 mg", "500 mg"], "BD", "5 days",
      "after food", "NSAID", [Department.ORTHOPEDICS]),
    M("ETOSHINE", "Etoshine", ["etoricoxib"], "Tablet", ["60 mg", "90 mg", "120 mg"], "OD",
      "5 days", "after food", "NSAID", [Department.ORTHOPEDICS]),
    M("MEFTAL_SPAS", "Meftal Spas", ["mefenamic acid", "dicyclomine"], "Tablet", ["250/10 mg"],
      "BD", "3 days", "after food", "Antispasmodic", [Department.GYNECOLOGY]),
    M("TRAMADOL", "Tramadol", ["tramadol"], "Capsule", ["50 mg"], "BD", "3 days", "after food",
      "Opioid analgesic", note="Prescribe cautiously; sedation and dependence risk"),
    M("VOLINI", "Volini Gel", ["diclofenac topical"], "Ointment", ["30 g", "50 g"],
      "apply locally BD", "7 days", None, "Topical analgesic", [Department.ORTHOPEDICS]),

    # ---------------------------- Gastro protection ------------------------
    M("PAN", "Pantoprazole", ["pantoprazole"], "Tablet", ["20 mg", "40 mg"], "OD", "7 days",
      "before breakfast", "Proton pump inhibitor"),
    M("PANTOP", "Pantop", ["pantoprazole"], "Tablet", ["40 mg"], "OD", "7 days",
      "before breakfast", "Proton pump inhibitor"),
    M("OMEZ", "Omez", ["omeprazole"], "Capsule", ["20 mg"], "OD", "7 days", "before breakfast",
      "Proton pump inhibitor"),
    M("RAZO", "Razo", ["rabeprazole"], "Tablet", ["20 mg"], "OD", "7 days", "before breakfast",
      "Proton pump inhibitor"),
    M("ONDEM", "Ondansetron", ["ondansetron"], "Tablet", ["4 mg", "8 mg"], "SOS", "3 days", None,
      "Antiemetic"),
    M("DOMSTAL", "Domperidone", ["domperidone"], "Tablet", ["10 mg"], "TDS", "3 days",
      "before food", "Prokinetic"),
    M("CYCLOPAM", "Cyclopam", ["dicyclomine", "paracetamol"], "Tablet", ["20/500 mg"], "TDS",
      "3 days", "after food", "Antispasmodic"),
    M("DROTIN", "Drotin", ["drotaverine"], "Tablet", ["40 mg", "80 mg"], "BD", "3 days",
      "after food", "Antispasmodic", [Department.GYNECOLOGY]),

    # ---------------------------- Bone / supplements -----------------------
    M("SHELCAL", "Shelcal 500", ["calcium", "vitamin d3"], "Tablet", ["500 mg + 250 IU"], "OD",
      "3 months", "after food", "Calcium supplement"),
    M("CALCIMAX", "Calcimax", ["calcium", "vitamin d3"], "Tablet", ["500 mg"], "OD", "3 months",
      "after food", "Calcium supplement"),
    M("UPRISE_D3", "Uprise D3", ["vitamin d3"], "Sachet", ["60000 IU"], "once weekly", "8 weeks",
      "after food", "Vitamin D supplement", note="Weekly sachet; not daily"),
    M("CALCIROL", "Calcirol", ["vitamin d3"], "Sachet", ["60000 IU"], "once weekly", "8 weeks",
      "after food", "Vitamin D supplement"),
    M("NUROKIND", "Nurokind", ["methylcobalamin"], "Tablet", ["500 mcg", "1500 mcg"], "OD",
      "1 month", "after food", "Vitamin B12"),
    M("NEUROBION", "Neurobion Forte", ["b complex"], "Tablet", [], "OD", "1 month", "after food",
      "Vitamin B complex"),
    M("OROFER_XT", "Orofer XT", ["iron", "folic acid"], "Tablet", ["100 mg + 1.5 mg"], "OD",
      "3 months", "after food", "Haematinic",
      note="Take with vitamin C; avoid with calcium or tea"),
    M("LIVOGEN", "Livogen", ["iron", "folic acid"], "Tablet", [], "OD", "3 months", "after food",
      "Haematinic"),
    M("FOLVITE", "Folvite", ["folic acid"], "Tablet", ["5 mg"], "OD", "3 months", "after food",
      "Folic acid", [Department.GYNECOLOGY]),

    # ---------------------------- Antibiotics ------------------------------
    M("AUGMENTIN", "Augmentin 625", ["amoxicillin", "clavulanic acid"], "Tablet", ["625 mg"],
      "BD", "5 days", "after food", "Antibiotic (penicillin)"),
    M("CLAVAM", "Clavam 625", ["amoxicillin", "clavulanic acid"], "Tablet", ["625 mg"], "BD",
      "5 days", "after food", "Antibiotic (penicillin)"),
    M("MOX", "Mox", ["amoxicillin"], "Capsule", ["250 mg", "500 mg"], "TDS", "5 days",
      "after food", "Antibiotic (penicillin)"),
    M("AZITHRAL", "Azithral", ["azithromycin"], "Tablet", ["250 mg", "500 mg"], "OD", "3 days",
      "before food", "Antibiotic (macrolide)"),
    M("TAXIM_O", "Taxim-O", ["cefixime"], "Tablet", ["200 mg"], "BD", "5 days", "after food",
      "Antibiotic (cephalosporin)"),
    M("CIFRAN", "Cifran", ["ciprofloxacin"], "Tablet", ["250 mg", "500 mg"], "BD", "5 days",
      "after food", "Antibiotic (quinolone)"),
    M("LEVOFLOX", "Levoflox", ["levofloxacin"], "Tablet", ["500 mg"], "OD", "5 days",
      "after food", "Antibiotic (quinolone)"),
    M("METROGYL", "Metrogyl", ["metronidazole"], "Tablet", ["200 mg", "400 mg"], "TDS", "5 days",
      "after food", "Antibiotic (antiprotozoal)",
      note="Avoid alcohol during and for 48 hours after"),
    M("DOXY", "Doxycycline", ["doxycycline"], "Capsule", ["100 mg"], "BD", "7 days",
      "after food", "Antibiotic (tetracycline)",
      note="Avoid in pregnancy; take with plenty of water, stay upright"),
    M("FLUCONAZOLE", "Fluconazole", ["fluconazole"], "Tablet", ["150 mg", "200 mg"], "STAT",
      "single dose", None, "Antifungal", [Department.GYNECOLOGY]),
    M("CLOTRIMAZOLE_V", "Clotrimazole Vaginal", ["clotrimazole"], "Tablet", ["100 mg", "500 mg"],
      "HS", "6 days", "at bedtime, per vaginam", "Antifungal", [Department.GYNECOLOGY]),

    # ---------------------------- Muscle relaxants / neuro ------------------
    M("MYORIL", "Myoril", ["thiocolchicoside"], "Capsule", ["4 mg", "8 mg"], "BD", "5 days",
      "after food", "Muscle relaxant", [Department.ORTHOPEDICS]),
    M("TIZAN", "Tizanidine", ["tizanidine"], "Tablet", ["2 mg"], "HS", "7 days", "at bedtime",
      "Muscle relaxant", [Department.ORTHOPEDICS], note="Causes drowsiness"),
    M("PREGABALIN", "Pregabalin", ["pregabalin"], "Capsule", ["75 mg", "150 mg"], "HS", "1 month",
      "at bedtime", "Neuropathic pain", [Department.ORTHOPEDICS]),
    M("GABAPENTIN", "Gabapentin", ["gabapentin"], "Capsule", ["100 mg", "300 mg"], "HS",
      "1 month", "at bedtime", "Neuropathic pain", [Department.ORTHOPEDICS]),

    # ---------------------------- Gynecology --------------------------------
    M("DUPHASTON", "Duphaston", ["dydrogesterone"], "Tablet", ["10 mg"], "BD", "10 days", None,
      "Progestogen", [Department.GYNECOLOGY]),
    M("SUSTEN", "Susten", ["progesterone"], "Capsule", ["100 mg", "200 mg", "400 mg"], "HS",
      "10 days", "at bedtime", "Progesterone", [Department.GYNECOLOGY]),
    M("MEPRATE", "Meprate", ["medroxyprogesterone"], "Tablet", ["10 mg"], "BD", "5 days", None,
      "Progestogen", [Department.GYNECOLOGY]),
    M("TRANEXAMIC", "Tranexamic Acid", ["tranexamic acid"], "Tablet", ["500 mg"], "TDS",
      "5 days", "after food", "Antifibrinolytic", [Department.GYNECOLOGY],
      note="For heavy menstrual bleeding; stop once bleeding settles"),
    M("PRIMOLUT", "Primolut N", ["norethisterone"], "Tablet", ["5 mg"], "BD", "10 days", None,
      "Progestogen", [Department.GYNECOLOGY]),
    M("LETROZOLE", "Letrozole", ["letrozole"], "Tablet", ["2.5 mg"], "OD", "5 days", None,
      "Ovulation induction", [Department.GYNECOLOGY],
      note="Day 2-6 of the cycle unless directed otherwise"),
    M("METFORMIN", "Metformin", ["metformin"], "Tablet", ["500 mg", "850 mg"], "BD", "3 months",
      "after food", "Antidiabetic / insulin sensitiser"),
    M("GLYCOMET", "Glycomet", ["metformin"], "Tablet", ["500 mg"], "BD", "3 months", "after food",
      "Antidiabetic"),
    M("MYOINOSITOL", "Myo-Inositol", ["myo-inositol"], "Sachet", ["2 g"], "BD", "3 months",
      "before food", "PCOS supplement", [Department.GYNECOLOGY]),
    M("ECOSPRIN_75", "Ecosprin 75", ["aspirin"], "Tablet", ["75 mg"], "OD", "as advised",
      "after food", "Antiplatelet"),

    # ---------------------------- Chronic / other ---------------------------
    M("THYRONORM", "Thyronorm", ["levothyroxine"], "Tablet",
      ["25 mcg", "50 mcg", "75 mcg", "100 mcg"], "OD", "continue", "empty stomach",
      "Thyroid hormone", note="Take on an empty stomach, 30-60 minutes before breakfast"),
    M("TELMA", "Telma", ["telmisartan"], "Tablet", ["20 mg", "40 mg"], "OD", "continue", None,
      "Antihypertensive"),
    M("AMLONG", "Amlong", ["amlodipine"], "Tablet", ["2.5 mg", "5 mg"], "OD", "continue", None,
      "Antihypertensive"),
    M("ATORVA", "Atorvastatin", ["atorvastatin"], "Tablet", ["10 mg", "20 mg"], "HS", "continue",
      "at bedtime", "Statin"),
    M("CETIRIZINE", "Cetirizine", ["cetirizine"], "Tablet", ["10 mg"], "HS", "5 days",
      "at bedtime", "Antihistamine"),
    M("LEVOCET", "Levocetirizine", ["levocetirizine"], "Tablet", ["5 mg"], "HS", "5 days",
      "at bedtime", "Antihistamine"),
    M("PREDNISOLONE", "Prednisolone", ["prednisolone"], "Tablet", ["5 mg", "10 mg", "20 mg"],
      "OD", "as advised", "after breakfast", "Corticosteroid",
      note="Taper as directed; do not stop abruptly"),
    M("ORS", "ORS Sachet", ["oral rehydration salts"], "Sachet", ["21.8 g"], "SOS", "3 days",
      None, "Rehydration"),
]

FORMULARY_BY_CODE: Dict[str, Medicine] = {item.code: item for item in FORMULARY}


# ---------------------------------------------------------------------------
# Deterministic interaction pairs
# ---------------------------------------------------------------------------
# Ingredient pairs with a well-established, clinically actionable interaction.
# Kept deliberately short: every entry here is one a prescriber should be
# stopped for. Broader or more speculative interactions remain the LLM
# copilot's job, clearly labelled as inference.
INTERACTION_PAIRS: Dict[Tuple[str, str], Tuple[str, str, str]] = {
    ("warfarin", "aspirin"): (
        "serious", "Markedly increased bleeding risk.",
        "Avoid the combination or monitor INR closely.",
    ),
    ("warfarin", "ibuprofen"): (
        "serious", "NSAIDs raise bleeding risk and displace warfarin.",
        "Prefer paracetamol for analgesia.",
    ),
    ("warfarin", "diclofenac"): (
        "serious", "NSAIDs raise bleeding risk with warfarin.",
        "Prefer paracetamol for analgesia.",
    ),
    ("warfarin", "metronidazole"): (
        "serious", "Metronidazole potentiates warfarin.",
        "Monitor INR; dose reduction is often needed.",
    ),
    ("methotrexate", "ibuprofen"): (
        "serious", "NSAIDs reduce methotrexate clearance and raise toxicity.",
        "Avoid; use paracetamol instead.",
    ),
    ("methotrexate", "aceclofenac"): (
        "serious", "NSAIDs reduce methotrexate clearance and raise toxicity.",
        "Avoid; use paracetamol instead.",
    ),
    ("methotrexate", "cotrimoxazole"): (
        "serious", "Additive antifolate effect causing marrow suppression.",
        "Avoid the combination.",
    ),
    ("tramadol", "pregabalin"): (
        "caution", "Additive sedation and CNS depression.",
        "Warn the patient about drowsiness; avoid driving.",
    ),
    ("tramadol", "gabapentin"): (
        "caution", "Additive sedation and CNS depression.",
        "Warn about drowsiness; avoid driving.",
    ),
    ("tramadol", "tizanidine"): (
        "caution", "Additive sedation.", "Warn about drowsiness.",
    ),
    ("metronidazole", "alcohol"): (
        "serious", "Disulfiram-like reaction.",
        "Counsel the patient to avoid alcohol during and 48 hours after the course.",
    ),
    ("ciprofloxacin", "calcium"): (
        "caution", "Calcium chelates fluoroquinolones and reduces absorption.",
        "Separate the doses by at least 2 hours.",
    ),
    ("levofloxacin", "calcium"): (
        "caution", "Calcium reduces fluoroquinolone absorption.",
        "Separate the doses by at least 2 hours.",
    ),
    ("doxycycline", "calcium"): (
        "caution", "Calcium chelates tetracyclines and reduces absorption.",
        "Separate the doses by at least 2 hours.",
    ),
    ("doxycycline", "iron"): (
        "caution", "Iron reduces doxycycline absorption.",
        "Separate the doses by at least 2 hours.",
    ),
    ("levothyroxine", "calcium"): (
        "caution", "Calcium reduces levothyroxine absorption.",
        "Separate by at least 4 hours; thyroxine on an empty stomach.",
    ),
    ("levothyroxine", "iron"): (
        "caution", "Iron reduces levothyroxine absorption.",
        "Separate by at least 4 hours.",
    ),
    ("levothyroxine", "pantoprazole"): (
        "caution", "Reduced gastric acid lowers levothyroxine absorption.",
        "Monitor TSH; separate the doses.",
    ),
    ("metformin", "contrast"): (
        "serious", "Risk of lactic acidosis around iodinated contrast studies.",
        "Withhold metformin around the contrast study as per protocol.",
    ),
    ("atorvastatin", "azithromycin"): (
        "caution", "Macrolides can raise statin levels and myopathy risk.",
        "Watch for muscle pain; consider pausing the statin during the course.",
    ),
    ("prednisolone", "ibuprofen"): (
        "caution", "Additive gastrointestinal ulceration risk.",
        "Add gastric protection if both are needed.",
    ),
    ("prednisolone", "aceclofenac"): (
        "caution", "Additive gastrointestinal ulceration risk.",
        "Add gastric protection if both are needed.",
    ),
    ("prednisolone", "diclofenac"): (
        "caution", "Additive gastrointestinal ulceration risk.",
        "Add gastric protection if both are needed.",
    ),
    ("tranexamic acid", "ecosprin"): (
        "caution", "Opposing effects on clotting.",
        "Review the indication for both.",
    ),
    ("fluconazole", "warfarin"): (
        "serious", "Fluconazole potentiates warfarin.",
        "Monitor INR closely.",
    ),
    ("ondansetron", "tramadol"): (
        "caution", "Both affect serotonin pathways.",
        "Watch for serotonin-related symptoms.",
    ),
}

# Ingredients that should not be prescribed in pregnancy.
PREGNANCY_CAUTIONS: Dict[str, Tuple[str, str]] = {
    "doxycycline": ("serious", "Tetracyclines are contraindicated in pregnancy."),
    "letrozole": ("serious", "Not for use once pregnancy is established."),
    "ibuprofen": ("caution", "NSAIDs are avoided in the third trimester."),
    "diclofenac": ("caution", "NSAIDs are avoided in the third trimester."),
    "aceclofenac": ("caution", "NSAIDs are avoided in the third trimester."),
    "naproxen": ("caution", "NSAIDs are avoided in the third trimester."),
    "etoricoxib": ("serious", "Not recommended in pregnancy."),
    "warfarin": ("serious", "Teratogenic; contraindicated in pregnancy."),
    "atorvastatin": ("serious", "Statins are contraindicated in pregnancy."),
    "ciprofloxacin": ("caution", "Fluoroquinolones are generally avoided in pregnancy."),
    "levofloxacin": ("caution", "Fluoroquinolones are generally avoided in pregnancy."),
    "tranexamic acid": ("caution", "Use only on a clear obstetric indication."),
}


def _haystack(item: Medicine) -> str:
    return " ".join(
        [item.code.lower(), item.name.lower(), item.category.lower(), *item.ingredients]
    )


_INDEX: Dict[str, str] = {item.code: _haystack(item) for item in FORMULARY}


def search(
    query: Optional[str] = None,
    *,
    department: Optional[Department] = None,
    limit: int = 30,
) -> List[Medicine]:
    """Rank formulary matches for autocomplete: name prefix beats ingredient."""
    pool = FORMULARY
    if department is not None:
        pool = [m for m in pool if not m.departments or department in m.departments]
    if not query or not query.strip():
        return sorted(pool, key=lambda m: m.name)[:limit]

    term = " ".join(query.lower().split())
    scored = []
    for item in pool:
        name = item.name.lower()
        if name == term:
            score = 0
        elif name.startswith(term):
            score = 1
        elif any(ingredient.startswith(term) for ingredient in item.ingredients):
            score = 2
        elif term in name:
            score = 3
        elif term in _INDEX[item.code]:
            score = 4
        else:
            continue
        scored.append((score, item.name, item))
    scored.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in scored[:limit]]


def get(code: str) -> Optional[Medicine]:
    return FORMULARY_BY_CODE.get(code)


def match_by_name(name: str) -> Optional[Medicine]:
    """Best formulary entry for a spoken or typed drug name."""
    cleaned = normalize_name(name)
    if not cleaned:
        return None
    for item in FORMULARY:
        if normalize_name(item.name) == cleaned:
            return item
    ingredients = ingredients_of(name)
    if ingredients:
        for item in FORMULARY:
            if set(item.ingredients) == ingredients:
                return item
    hits = search(cleaned, limit=1)
    return hits[0] if hits else None


def ingredients_for(name: str, code: Optional[str] = None) -> Set[str]:
    if code:
        item = get(code)
        if item:
            return set(item.ingredients)
    matched = match_by_name(name)
    if matched:
        return set(matched.ingredients)
    return ingredients_of(name)


def class_of(ingredient: str) -> Optional[str]:
    return DRUG_CLASSES.get(ingredient)
