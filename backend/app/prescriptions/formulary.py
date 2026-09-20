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
from app.core.config import settings
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
    # Drafted here and not yet signed off by a consultant of that speciality.
    # Provisional entries are withheld until the department is named in
    # APPROVED_FORMULARY — see `_approved_departments` below.
    provisional: bool = False


M = Medicine


@dataclass(frozen=True)
class MedicineTemplate:
  disease_name: str
  keywords: List[str]
  medicine_codes: List[str]
  department: Department
  note: str = "Doctor review required before issuing."
  provisional: bool = False

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

    # -------------------------- Gastroenterology ----------------------------
    # DRAFTED, NOT YET APPROVED. Every entry below is provisional=True and is
    # withheld from prescribing until a gastroenterologist signs it off and the
    # department is named in APPROVED_FORMULARY. Strengths and frequencies are
    # the common adult starting points, to be confirmed by the prescriber for
    # the patient in front of them; nothing here adjusts for renal or hepatic
    # impairment, pregnancy, or childhood dosing.
    # Eradication dosing is twice daily for the full fourteen days, which is
    # not the once-daily reflux dose. Kept as its own entry because pointing a
    # regimen at the 7-day PPI leaves the patient on antibiotics for a week
    # after the acid suppression has run out.
    M("PAN_40_OD", "Pantoprazole (healing course)", ["pantoprazole"], "Tablet", ["40 mg"],
      "OD", "4 weeks", "before breakfast", "Proton pump inhibitor",
      [Department.GASTROENTEROLOGY],
      note="Reflux and ulcer healing run in weeks, not days; review before repeating",
      provisional=True),
    M("PAN_40_BD", "Pantoprazole (eradication dose)", ["pantoprazole"], "Tablet", ["40 mg"],
      "BD", "14 days", "before food", "Proton pump inhibitor", [Department.GASTROENTEROLOGY],
      note="Twice-daily dosing, for H. pylori eradication", provisional=True),
    M("ESOMEP", "Esomeprazole", ["esomeprazole"], "Tablet", ["20 mg", "40 mg"], "OD", "14 days",
      "before breakfast", "Proton pump inhibitor", [Department.GASTROENTEROLOGY], provisional=True),
    M("LANSOP", "Lansoprazole", ["lansoprazole"], "Capsule", ["15 mg", "30 mg"], "OD", "14 days",
      "before breakfast", "Proton pump inhibitor", [Department.GASTROENTEROLOGY], provisional=True),
    M("PAN_D", "Pantoprazole + Domperidone", ["pantoprazole", "domperidone"], "Capsule",
      ["40/30 mg"], "OD", "14 days", "before breakfast", "PPI + prokinetic", [Department.GASTROENTEROLOGY],
      note="Domperidone: use the lowest dose for the shortest time", provisional=True),
    M("FAMOTIDINE", "Famotidine", ["famotidine"], "Tablet", ["20 mg", "40 mg"], "BD", "14 days",
      "after food", "H2 receptor blocker", [Department.GASTROENTEROLOGY], provisional=True),
    M("SUCRALFATE", "Sucralfate", ["sucralfate"], "Syrup", ["1 g/10 mL"], "TDS", "14 days",
      "1 hour before food", "Mucosal protective", [Department.GASTROENTEROLOGY],
      note="Separate from other medicines by two hours", provisional=True),
    M("GELUSIL", "Antacid Gel (Magaldrate + Simethicone)", ["magaldrate", "simethicone"],
      "Syrup", ["10 mL"], "SOS", "7 days", "after food and at bedtime", "Antacid", [Department.GASTROENTEROLOGY],
      provisional=True),
    M("ITOPRIDE", "Itopride", ["itopride"], "Tablet", ["50 mg"], "TDS", "14 days",
      "before food", "Prokinetic", [Department.GASTROENTEROLOGY], provisional=True),
    M("LEVOSULPIRIDE", "Levosulpiride", ["levosulpiride"], "Tablet", ["25 mg"], "TDS", "7 days",
      "before food", "Prokinetic", [Department.GASTROENTEROLOGY],
      note="Avoid prolonged courses: extrapyramidal effects", provisional=True),

    # Antiemetics and antispasmodics
    M("DOMPERIDONE_10", "Domperidone", ["domperidone"], "Tablet", ["10 mg"], "TDS", "5 days",
      "before food", "Antiemetic / prokinetic", [Department.GASTROENTEROLOGY], provisional=True),
    M("ONDEM_MD", "Ondansetron MD", ["ondansetron"], "Tablet", ["4 mg", "8 mg"], "SOS", "3 days",
      "dissolves on the tongue", "Antiemetic", [Department.GASTROENTEROLOGY], provisional=True),
    M("MEBEVERINE", "Mebeverine", ["mebeverine"], "Tablet", ["135 mg"], "TDS", "14 days",
      "20 minutes before food", "Antispasmodic", [Department.GASTROENTEROLOGY], provisional=True),
    M("DICYCLOMINE", "Dicyclomine", ["dicyclomine"], "Tablet", ["10 mg", "20 mg"], "TDS",
      "3 days", "before food", "Antispasmodic", [Department.GASTROENTEROLOGY], provisional=True),

    # Bowel
    M("LACTULOSE", "Lactulose", ["lactulose"], "Syrup", ["10 g/15 mL"], "HS", "as advised",
      "at bedtime", "Osmotic laxative", [Department.GASTROENTEROLOGY], provisional=True),
    M("ISABGOL", "Isabgol (Psyllium Husk)", ["ispaghula"], "Sachet", ["5 g"], "HS", "as advised",
      "with a full glass of water at bedtime", "Bulk laxative", [Department.GASTROENTEROLOGY],
      note="Must be taken with plenty of water", provisional=True),
    M("PEG_SACHET", "Polyethylene Glycol 3350", ["polyethylene glycol"], "Sachet", ["17 g"],
      "OD", "as advised", "dissolved in water", "Osmotic laxative", [Department.GASTROENTEROLOGY], provisional=True),
    M("BISACODYL", "Bisacodyl", ["bisacodyl"], "Tablet", ["5 mg"], "HS", "3 days",
      "at bedtime", "Stimulant laxative", [Department.GASTROENTEROLOGY],
      note="Short courses only", provisional=True),
    M("LOPERAMIDE", "Loperamide", ["loperamide"], "Tablet", ["2 mg"], "SOS", "2 days", None,
      "Antidiarrhoeal", [Department.GASTROENTEROLOGY],
      note="Not for bloody diarrhoea or suspected colitis", provisional=True),
    M("RACECADOTRIL", "Racecadotril", ["racecadotril"], "Capsule", ["100 mg"], "TDS", "3 days",
      "before food", "Antidiarrhoeal", [Department.GASTROENTEROLOGY], provisional=True),
    M("PROBIOTIC", "Probiotic (Saccharomyces boulardii)", ["saccharomyces boulardii"], "Sachet",
      ["250 mg"], "BD", "7 days", "after food", "Probiotic", [Department.GASTROENTEROLOGY], provisional=True),
    M("RIFAXIMIN", "Rifaximin", ["rifaximin"], "Tablet", ["200 mg", "400 mg", "550 mg"], "BD",
      "as advised", "after food", "Gut-selective antibiotic", [Department.GASTROENTEROLOGY], provisional=True),
    M("MESALAMINE", "Mesalamine", ["mesalamine"], "Tablet", ["400 mg", "800 mg", "1.2 g"], "BD",
      "as advised", "after food", "Aminosalicylate", [Department.GASTROENTEROLOGY],
      note="Maintenance therapy: continue as directed", provisional=True),

    # Liver
    M("UDCA", "Ursodeoxycholic Acid", ["ursodeoxycholic acid"], "Tablet", ["150 mg", "300 mg"],
      "BD", "as advised", "after food", "Bile acid", [Department.GASTROENTEROLOGY], provisional=True),
    M("SILYMARIN", "Silymarin", ["silymarin"], "Tablet", ["140 mg"], "TDS", "as advised",
      "after food", "Hepatoprotective", [Department.GASTROENTEROLOGY], provisional=True),
    M("LOLA", "L-Ornithine L-Aspartate", ["l-ornithine l-aspartate"], "Sachet", ["3 g"], "TDS",
      "as advised", "in water after food", "Hepatic support", [Department.GASTROENTEROLOGY], provisional=True),
    M("PROPRANOLOL", "Propranolol", ["propranolol"], "Tablet", ["10 mg", "20 mg", "40 mg"], "BD",
      "continue", "after food", "Non-selective beta blocker", [Department.GASTROENTEROLOGY],
      note="For variceal prophylaxis: titrate to heart rate as directed", provisional=True),

    # Enzymes and H. pylori components
    M("PANCREATIN", "Pancreatic Enzyme (Lipase-Protease-Amylase)", ["pancreatin"], "Capsule",
      ["10000 IU", "25000 IU"], "TDS", "as advised", "with meals",
      "Pancreatic enzyme replacement", [Department.GASTROENTEROLOGY], provisional=True),
    M("CLARITHROMYCIN", "Clarithromycin", ["clarithromycin"], "Tablet", ["250 mg", "500 mg"],
      "BD", "14 days", "after food", "Macrolide antibiotic", [Department.GASTROENTEROLOGY], provisional=True),
    M("AMOX_500", "Amoxicillin 500", ["amoxicillin"], "Capsule", ["500 mg"], "BD", "14 days",
      "after food", "Penicillin antibiotic", [Department.GASTROENTEROLOGY], provisional=True),
    M("TINIDAZOLE", "Tinidazole", ["tinidazole"], "Tablet", ["500 mg"], "BD", "14 days",
      "after food", "Nitroimidazole", [Department.GASTROENTEROLOGY],
      note="No alcohol during the course and for three days after", provisional=True),
    M("LEVOFLOXACIN", "Levofloxacin", ["levofloxacin"], "Tablet", ["250 mg", "500 mg"], "OD",
      "as advised", "after food", "Fluoroquinolone", [Department.GASTROENTEROLOGY],
      note="Second-line H. pylori regimens only; tendon and QT cautions", provisional=True),
    M("BISMUTH", "Colloidal Bismuth Subcitrate", ["bismuth subcitrate"], "Tablet", ["120 mg"],
      "QID", "14 days", "before food", "Bismuth salt", [Department.GASTROENTEROLOGY],
      note="Blackens the tongue and stool — tell the patient, or they will think it is bleeding",
      provisional=True),
]


FORMULARY_BY_CODE: Dict[str, Medicine] = {item.code: item for item in FORMULARY}

MEDICINE_TEMPLATES: List[MedicineTemplate] = [
  MedicineTemplate(
    "Olecranon fracture with tendon injury",
    ["olecranon", "elbow fracture", "fracture elbow", "tendon injury"],
    ["PARA", "PAN", "CALCIMAX"], Department.ORTHOPEDICS,
  ),
  MedicineTemplate(
    "Acute musculoskeletal pain",
    ["musculoskeletal pain", "joint pain", "sprain", "strain"],
    ["PARA", "PAN"], Department.ORTHOPEDICS,
  ),
  MedicineTemplate(
    "Neuropathic pain",
    ["neuropathic pain", "nerve pain", "radicular pain"],
    ["PARA", "PREGABALIN"], Department.ORTHOPEDICS,
  ),
  MedicineTemplate(
    "Dysmenorrhea",
    ["dysmenorrhea", "period pain", "menstrual pain", "cramps"],
    ["MEFTAL_SPAS", "PAN"], Department.GYNECOLOGY,
  ),
  MedicineTemplate(
    "Heavy menstrual bleeding",
    ["heavy menstrual bleeding", "heavy periods", "menorrhagia"],
    ["TRANEXAMIC", "MEFTAL_SPAS"], Department.GYNECOLOGY,
  ),
  MedicineTemplate(
    "Polycystic ovary syndrome",
    ["polycystic ovary", "pcos", "pcod"],
    ["METFORMIN", "MYOINOSITOL"], Department.GYNECOLOGY,
  ),

  # ------------------------- Gastroenterology ------------------------------
  # DRAFTED, NOT YET APPROVED — every one is provisional and withheld until a
  # gastroenterologist signs them off. A template is a whole regimen, so it is
  # the part of this file that most needs a consultant's name against it.
  MedicineTemplate(
    "Gastro-oesophageal reflux disease",
    ["gerd", "reflux", "acidity", "heartburn", "acid reflux"],
    ["PAN_40_OD", "GELUSIL"], Department.GASTROENTEROLOGY,
    note="Doctor review required. Advise weight, late meals and smoking first.",
    provisional=True,
  ),
  MedicineTemplate(
    "Functional dyspepsia",
    ["dyspepsia", "indigestion", "gas", "bloating", "fullness"],
    ["PAN_D", "ITOPRIDE"], Department.GASTROENTEROLOGY,
    note="Doctor review required. Exclude alarm features before treating empirically.",
    provisional=True,
  ),
  MedicineTemplate(
    "H. pylori eradication — first line (14 days)",
    ["h pylori", "helicobacter", "hp eradication", "triple therapy"],
    ["PAN_40_BD", "AMOX_500", "CLARITHROMYCIN"], Department.GASTROENTEROLOGY,
    note=(
      "Doctor review required. Fourteen days, all three together, twice daily. "
      "Confirm eradication four weeks after finishing, off PPI for two weeks. "
      "Check penicillin allergy and local clarithromycin resistance before use."
    ),
    provisional=True,
  ),
  MedicineTemplate(
    "H. pylori eradication — bismuth quadruple",
    ["h pylori second line", "quadruple therapy", "bismuth"],
    ["PAN_40_BD", "BISMUTH", "TINIDAZOLE", "AMOX_500"], Department.GASTROENTEROLOGY,
    note=(
      "Doctor review required. For penicillin allergy or a failed first course, "
      "where the antibiotic choice changes — do not repeat what has already failed."
    ),
    provisional=True,
  ),
  MedicineTemplate(
    "Peptic ulcer disease",
    ["peptic ulcer", "gastric ulcer", "duodenal ulcer", "ulcer"],
    ["PAN_40_OD", "SUCRALFATE"], Department.GASTROENTEROLOGY,
    note="Doctor review required. Stop NSAIDs; test for H. pylori.",
    provisional=True,
  ),
  MedicineTemplate(
    "Acute gastroenteritis",
    ["gastroenteritis", "loose motions", "diarrhoea", "diarrhea", "food poisoning"],
    ["ORS", "PROBIOTIC", "ONDEM_MD"], Department.GASTROENTEROLOGY,
    note=(
      "Doctor review required. Rehydration is the treatment. No antimotility "
      "drug where there is blood in the stool or a fever."
    ),
    provisional=True,
  ),
  MedicineTemplate(
    "Irritable bowel syndrome — diarrhoea predominant",
    ["ibs", "ibs-d", "irritable bowel"],
    ["MEBEVERINE", "PROBIOTIC"], Department.GASTROENTEROLOGY,
    note="Doctor review required. A diagnosis of exclusion; review the alarm features.",
    provisional=True,
  ),
  MedicineTemplate(
    "Irritable bowel syndrome — constipation predominant",
    ["ibs-c", "constipation predominant"],
    ["MEBEVERINE", "ISABGOL"], Department.GASTROENTEROLOGY,
    note="Doctor review required. Fibre and fluids before anything else.",
    provisional=True,
  ),
  MedicineTemplate(
    "Chronic constipation",
    ["constipation", "hard stool", "kabz"],
    ["ISABGOL", "LACTULOSE"], Department.GASTROENTEROLOGY,
    note="Doctor review required. Review the drugs the patient already takes.",
    provisional=True,
  ),
  MedicineTemplate(
    "Non-alcoholic fatty liver disease",
    ["nafld", "fatty liver", "hepatic steatosis"],
    ["SILYMARIN", "UDCA"], Department.GASTROENTEROLOGY,
    note=(
      "Doctor review required. Weight loss and glycaemic control are the "
      "treatment; medicines are adjuncts."
    ),
    provisional=True,
  ),
  MedicineTemplate(
    "Gallstone disease — symptomatic",
    ["gallstones", "cholelithiasis", "biliary colic"],
    ["DROTIN", "PARA"], Department.GASTROENTEROLOGY,
    note=(
      "Doctor review required. Antispasmodic and simple analgesia for the "
      "attack; surgical referral where they recur. Avoid NSAIDs here."
    ),
    provisional=True,
  ),
]


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

    # Gastroenterology. These arrived with the H. pylori regimens: a fourteen-day
    # course of clarithromycin is prescribed to outpatients who are frequently
    # already on a statin or a blood thinner, and the harm lands after they have
    # gone home. Unlike the formulary entries above, these are not gated behind
    # sign-off — a warning that only appears once the content is approved is a
    # warning missing for exactly as long as it is most needed.
    ("clarithromycin", "atorvastatin"): (
        "serious", "Clarithromycin blocks statin metabolism; risk of rhabdomyolysis.",
        "Hold the statin for the course, or use a regimen without clarithromycin.",
    ),
    ("clarithromycin", "simvastatin"): (
        "serious", "Contraindicated together; severe myopathy risk.",
        "Stop the statin for the course or change the antibiotic.",
    ),
    ("clarithromycin", "warfarin"): (
        "serious", "Clarithromycin potentiates warfarin.",
        "Monitor INR during and after the course.",
    ),
    ("clarithromycin", "domperidone"): (
        "serious", "Both prolong the QT interval; additive arrhythmia risk.",
        "Use a different prokinetic during the eradication course.",
    ),
    ("clarithromycin", "colchicine"): (
        "serious", "Clarithromycin raises colchicine levels; toxicity can be fatal.",
        "Avoid the combination.",
    ),
    ("tinidazole", "alcohol"): (
        "serious", "Disulfiram-like reaction.",
        "No alcohol during the course and for three days after.",
    ),
    ("tinidazole", "warfarin"): (
        "serious", "Nitroimidazoles potentiate warfarin.",
        "Monitor INR closely.",
    ),
    ("clopidogrel", "omeprazole"): (
        "serious", "Omeprazole reduces the antiplatelet effect of clopidogrel.",
        "Use pantoprazole instead.",
    ),
    ("clopidogrel", "esomeprazole"): (
        "serious", "Esomeprazole reduces the antiplatelet effect of clopidogrel.",
        "Use pantoprazole instead.",
    ),
    ("domperidone", "ondansetron"): (
        "caution", "Additive QT prolongation.",
        "Use one antiemetic at a time where the heart is a concern.",
    ),
    ("levofloxacin", "domperidone"): (
        "caution", "Additive QT prolongation.",
        "Review the need for both.",
    ),
    ("sucralfate", "levothyroxine"): (
        "caution", "Sucralfate binds levothyroxine and reduces its absorption.",
        "Separate the doses by at least two hours.",
    ),
    ("sucralfate", "ciprofloxacin"): (
        "caution", "Sucralfate binds fluoroquinolones and reduces absorption.",
        "Separate the doses by at least two hours.",
    ),
    ("loperamide", "ondansetron"): (
        "caution", "Both prolong the QT interval at higher doses.",
        "Keep loperamide to short, low-dose use.",
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


def _is_available(item) -> bool:
    """Whether a drafted entry may be prescribed here yet.

    An entry marked provisional was written by whoever added the speciality,
    not by a consultant who practises it. It stays out of the prescribing
    screens until its department is named in APPROVED_FORMULARY. An entry with
    no department is general content that shipped with the platform.
    """
    if not getattr(item, "provisional", False):
        return True
    approved = settings.approved_formulary_departments
    departments = (
        [item.department] if isinstance(item, MedicineTemplate) else item.departments
    )
    return bool(departments) and all(d in approved for d in departments)


def available_formulary() -> List[Medicine]:
    """The medicines this installation may actually prescribe today."""
    return [item for item in FORMULARY if _is_available(item)]


def unapproved_departments() -> List[Department]:
    """Departments carrying drafted content nobody has signed off, for the log."""
    approved = settings.approved_formulary_departments
    pending = {
        department
        for item in FORMULARY
        if getattr(item, "provisional", False)
        for department in item.departments
        if department not in approved
    }
    pending.update(
        template.department
        for template in MEDICINE_TEMPLATES
        if template.provisional and template.department not in approved
    )
    return sorted(pending, key=lambda d: d.value)


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
    pool = available_formulary()
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


def search_templates(
    query: Optional[str] = None,
    *,
    department: Optional[Department] = None,
    limit: int = 20,
) -> List[MedicineTemplate]:
    """Find doctor-reviewed medicine templates by disease name or keyword."""
    pool = [
      template for template in MEDICINE_TEMPLATES
      if (department is None or template.department == department)
      and _is_available(template)
    ]
    if not query or not query.strip():
      return pool[:limit]
    terms = " ".join(query.lower().split())
    query_words = set(terms.split())
    ranked = []
    for template in pool:
        haystack = " ".join([template.disease_name.lower(), *template.keywords])
        if terms == template.disease_name.lower():
            score = 0
        elif template.disease_name.lower().startswith(terms):
            score = 1
        elif terms in haystack:
            score = 2
        elif any(keyword.lower() in query_words for keyword in template.keywords):
            score = 3
        elif any(keyword.lower() in terms for keyword in template.keywords):
            score = 4
        else:
            continue
        ranked.append((score, template.disease_name, template))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in ranked[:limit]]


def get(code: str) -> Optional[Medicine]:
    """Look a medicine up by code, unless it is drafted and unapproved.

    Reached from the prescribing screen and from a template's medicine list,
    so withholding it here is what stops an unapproved drug being prescribed
    by anyone who knows its code.
    """
    item = FORMULARY_BY_CODE.get(code)
    return item if item is not None and _is_available(item) else None


def get_including_unapproved(code: str) -> Optional[Medicine]:
    """For reading an existing prescription, where the drug was already given.

    A prescription already issued names what the patient is taking. Hiding the
    entry afterwards would make an old prescription unreadable, which helps
    nobody; the control belongs at the point of prescribing.
    """
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
    """What a prescribed medicine contains, for the duplicate and interaction checks.

    Resolves a drafted entry too. Knowing what a drug contains is never a
    decision to prescribe it — it is the check that catches the clarithromycin
    already on the patient's list — and a safety check that goes quiet because
    content is awaiting sign-off would be worse than no gate at all.
    """
    if code:
        item = get_including_unapproved(code)
        if item:
            return set(item.ingredients)
    matched = match_by_name(name)
    if matched:
        return set(matched.ingredients)
    return ingredients_of(name)


def class_of(ingredient: str) -> Optional[str]:
    return DRUG_CLASSES.get(ingredient)
