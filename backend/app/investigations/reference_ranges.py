"""Reference ranges for analytes reported by Indian laboratories.

These drive the deterministic half of report analysis: comparing a printed
value against an expected interval is arithmetic, not inference, so it is done
here rather than by a language model.

Precedence at analysis time:
  1. the range printed on the report itself (labs differ in method and units)
  2. these built-in ranges, matched on sex and age
A range is only applied when the units agree, or when a known conversion
exists — a mismatched unit yields "unknown" rather than a wrong flag.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.enums import Gender


@dataclass(frozen=True)
class ReferenceRange:
    analyte: str
    unit: str
    low: Optional[float] = None
    high: Optional[float] = None
    sex: Optional[Gender] = None          # None = applies to all
    min_age: int = 0
    max_age: int = 120
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None
    aliases: List[str] = field(default_factory=list)
    note: Optional[str] = None


# Canonical analyte key -> ranges (multiple entries allow sex/age variants).
REFERENCE_RANGES: Dict[str, List[ReferenceRange]] = {
    # ---------------- Haematology ----------------
    "hemoglobin": [
        ReferenceRange("Hemoglobin", "g/dL", 13.0, 17.0, Gender.MALE, 15, 120, 7.0, 20.0,
                       aliases=["hb", "haemoglobin", "hgb"]),
        ReferenceRange("Hemoglobin", "g/dL", 12.0, 15.0, Gender.FEMALE, 15, 120, 7.0, 20.0,
                       aliases=["hb", "haemoglobin", "hgb"]),
        ReferenceRange("Hemoglobin", "g/dL", 11.5, 15.5, None, 0, 14, 7.0, 20.0,
                       aliases=["hb", "haemoglobin", "hgb"]),
    ],
    "total_leukocyte_count": [
        ReferenceRange("Total Leukocyte Count", "cells/cumm", 4000, 11000, None, 0, 120, 2000, 30000,
                       aliases=["tlc", "wbc", "white blood cell count", "total wbc count", "leucocyte count"]),
    ],
    "platelet_count": [
        ReferenceRange("Platelet Count", "lakh/cumm", 1.5, 4.1, None, 0, 120, 0.5, 10.0,
                       aliases=["platelets", "plt"]),
    ],
    "packed_cell_volume": [
        ReferenceRange("Packed Cell Volume", "%", 40, 50, Gender.MALE, 15, 120,
                       aliases=["pcv", "hematocrit", "haematocrit", "hct"]),
        ReferenceRange("Packed Cell Volume", "%", 36, 46, Gender.FEMALE, 15, 120,
                       aliases=["pcv", "hematocrit", "haematocrit", "hct"]),
    ],
    "esr": [
        ReferenceRange("ESR", "mm/hr", 0, 15, Gender.MALE, 0, 120,
                       aliases=["erythrocyte sedimentation rate"]),
        ReferenceRange("ESR", "mm/hr", 0, 20, Gender.FEMALE, 0, 120,
                       aliases=["erythrocyte sedimentation rate"]),
    ],
    "mcv": [ReferenceRange("MCV", "fL", 83, 101, aliases=["mean corpuscular volume"])],
    "mch": [ReferenceRange("MCH", "pg", 27, 32, aliases=["mean corpuscular hemoglobin"])],
    "mchc": [ReferenceRange("MCHC", "g/dL", 31.5, 34.5)],
    "rbc_count": [
        ReferenceRange("RBC Count", "million/cumm", 4.5, 5.5, Gender.MALE, 15, 120, aliases=["rbc"]),
        ReferenceRange("RBC Count", "million/cumm", 3.8, 4.8, Gender.FEMALE, 15, 120, aliases=["rbc"]),
    ],

    # ---------------- Biochemistry ----------------
    "fasting_glucose": [
        ReferenceRange("Fasting Blood Sugar", "mg/dL", 70, 100, None, 0, 120, 50, 400,
                       aliases=["fbs", "fasting blood glucose", "glucose fasting", "fasting plasma glucose"]),
    ],
    "postprandial_glucose": [
        ReferenceRange("Post Prandial Blood Sugar", "mg/dL", 70, 140, None, 0, 120, 50, 400,
                       aliases=["ppbs", "pp blood sugar", "post prandial glucose", "glucose pp"]),
    ],
    "random_glucose": [
        ReferenceRange("Random Blood Sugar", "mg/dL", 70, 140, None, 0, 120, 50, 400,
                       aliases=["rbs", "random blood glucose"]),
    ],
    "hba1c": [
        ReferenceRange("HbA1c", "%", 4.0, 5.6, None, 0, 120, None, 10.0,
                       aliases=["glycated hemoglobin", "glycosylated hemoglobin", "a1c"],
                       note="5.7-6.4% prediabetes; >=6.5% diabetes range"),
    ],
    "urea": [ReferenceRange("Blood Urea", "mg/dL", 15, 40, None, 0, 120, None, 100,
                            aliases=["urea", "blood urea nitrogen"])],
    "creatinine": [
        ReferenceRange("Serum Creatinine", "mg/dL", 0.7, 1.3, Gender.MALE, 15, 120, None, 4.0,
                       aliases=["creatinine", "s. creatinine"]),
        ReferenceRange("Serum Creatinine", "mg/dL", 0.6, 1.1, Gender.FEMALE, 15, 120, None, 4.0,
                       aliases=["creatinine", "s. creatinine"]),
    ],
    "uric_acid": [
        ReferenceRange("Uric Acid", "mg/dL", 3.5, 7.2, Gender.MALE, 15, 120),
        ReferenceRange("Uric Acid", "mg/dL", 2.6, 6.0, Gender.FEMALE, 15, 120),
    ],
    "sodium": [ReferenceRange("Sodium", "mEq/L", 136, 145, None, 0, 120, 120, 160, aliases=["na+", "na"])],
    "potassium": [ReferenceRange("Potassium", "mEq/L", 3.5, 5.1, None, 0, 120, 2.5, 6.5, aliases=["k+", "k"])],
    "calcium": [ReferenceRange("Calcium", "mg/dL", 8.6, 10.2, None, 0, 120, 6.0, 13.0,
                               aliases=["serum calcium", "total calcium"])],
    "phosphorus": [ReferenceRange("Phosphorus", "mg/dL", 2.5, 4.5, aliases=["phosphate", "inorganic phosphorus"])],
    "alkaline_phosphatase": [ReferenceRange("Alkaline Phosphatase", "U/L", 40, 129, aliases=["alp", "s. alkaline phosphatase"])],
    "sgpt": [ReferenceRange("SGPT (ALT)", "U/L", 0, 50, aliases=["alt", "sgpt", "alanine aminotransferase"])],
    "sgot": [ReferenceRange("SGOT (AST)", "U/L", 0, 50, aliases=["ast", "sgot", "aspartate aminotransferase"])],
    "total_bilirubin": [ReferenceRange("Total Bilirubin", "mg/dL", 0.2, 1.2, None, 0, 120, None, 15.0,
                                       aliases=["bilirubin total", "s. bilirubin"])],
    "direct_bilirubin": [ReferenceRange("Direct Bilirubin", "mg/dL", 0.0, 0.3,
                                        aliases=["conjugated bilirubin", "bilirubin direct"])],
    "ggt": [ReferenceRange("Gamma GT", "U/L", 8, 61, Gender.MALE, 15, 120,
                           aliases=["ggt", "gamma gt", "gamma glutamyl transferase", "ggtp"]),
            ReferenceRange("Gamma GT", "U/L", 5, 36, Gender.FEMALE, 15, 120,
                           aliases=["ggt", "gamma gt", "gamma glutamyl transferase", "ggtp"])],
    # Raised three times over in acute pancreatitis; the critical value is what
    # makes the report worth reading the same hour it arrives.
    "amylase": [ReferenceRange("Serum Amylase", "U/L", 25, 125, None, 0, 120, None, 375,
                               aliases=["s. amylase", "amylase serum"])],
    "lipase": [ReferenceRange("Serum Lipase", "U/L", 13, 60, None, 0, 120, None, 180,
                              aliases=["s. lipase", "lipase serum"])],
    "total_protein": [ReferenceRange("Total Protein", "g/dL", 6.4, 8.3)],
    "albumin": [ReferenceRange("Albumin", "g/dL", 3.5, 5.2, aliases=["s. albumin"])],
    "total_cholesterol": [ReferenceRange("Total Cholesterol", "mg/dL", 0, 200, aliases=["cholesterol total"])],
    "ldl": [ReferenceRange("LDL Cholesterol", "mg/dL", 0, 100, aliases=["ldl", "ldl-c"])],
    "hdl": [ReferenceRange("HDL Cholesterol", "mg/dL", 40, 100, aliases=["hdl", "hdl-c"])],
    "triglycerides": [ReferenceRange("Triglycerides", "mg/dL", 0, 150, aliases=["tg"])],
    "vitamin_d": [ReferenceRange("Vitamin D (25-OH)", "ng/mL", 30, 100, None, 0, 120, None, 150,
                                 aliases=["25 oh vitamin d", "vitamin d3", "25-hydroxyvitamin d"])],
    "vitamin_b12": [ReferenceRange("Vitamin B12", "pg/mL", 211, 911, aliases=["b12", "cobalamin"])],
    "ferritin": [
        ReferenceRange("Ferritin", "ng/mL", 30, 400, Gender.MALE, 15, 120),
        ReferenceRange("Ferritin", "ng/mL", 13, 150, Gender.FEMALE, 15, 120),
    ],
    "serum_iron": [ReferenceRange("Serum Iron", "ug/dL", 65, 175, aliases=["iron"])],
    "crp": [ReferenceRange("CRP", "mg/L", 0, 5, aliases=["c reactive protein", "c-reactive protein"])],
    "ra_factor": [ReferenceRange("Rheumatoid Factor", "IU/mL", 0, 14, aliases=["ra factor", "rf"])],
    "anti_ccp": [ReferenceRange("Anti-CCP", "U/mL", 0, 17, aliases=["anti ccp", "acpa"])],

    # ---------------- Hormonal ----------------
    "tsh": [ReferenceRange("TSH", "uIU/mL", 0.4, 4.0, None, 0, 120, None, 20.0,
                           aliases=["thyroid stimulating hormone", "s. tsh"])],
    "t3": [ReferenceRange("T3 (Total)", "ng/dL", 80, 200, aliases=["total t3", "triiodothyronine"])],
    "t4": [ReferenceRange("T4 (Total)", "ug/dL", 5.1, 14.1, aliases=["total t4", "thyroxine"])],
    "free_t4": [ReferenceRange("Free T4", "ng/dL", 0.89, 1.76, aliases=["ft4"])],
    "free_t3": [ReferenceRange("Free T3", "pg/mL", 2.3, 4.2, aliases=["ft3"])],
    "prolactin": [
        ReferenceRange("Prolactin", "ng/mL", 4.0, 15.2, Gender.MALE, 15, 120),
        ReferenceRange("Prolactin", "ng/mL", 4.8, 23.3, Gender.FEMALE, 15, 120),
    ],
    "fsh": [ReferenceRange("FSH", "mIU/mL", 1.5, 12.4, None, 0, 120,
                           aliases=["follicle stimulating hormone"],
                           note="Cycle-phase dependent in women; interpret with LMP")],
    "lh": [ReferenceRange("LH", "mIU/mL", 1.7, 8.6, None, 0, 120,
                          aliases=["luteinizing hormone"],
                          note="Cycle-phase dependent in women")],
    "estradiol": [ReferenceRange("Estradiol (E2)", "pg/mL", 12.5, 166.0, Gender.FEMALE, 15, 120,
                                 aliases=["e2", "oestradiol"], note="Follicular phase reference")],
    "progesterone": [ReferenceRange("Progesterone", "ng/mL", 0.1, 0.8, Gender.FEMALE, 15, 120,
                                    note="Follicular phase; rises markedly in luteal phase")],
    "testosterone": [
        ReferenceRange("Testosterone (Total)", "ng/dL", 249, 836, Gender.MALE, 15, 120),
        ReferenceRange("Testosterone (Total)", "ng/dL", 8, 60, Gender.FEMALE, 15, 120),
    ],
    "amh": [ReferenceRange("AMH", "ng/mL", 1.0, 4.0, Gender.FEMALE, 15, 45,
                           aliases=["anti mullerian hormone"])],
    "beta_hcg": [ReferenceRange("Beta hCG", "mIU/mL", 0, 5, None, 0, 120,
                                aliases=["b-hcg", "beta hcg", "hcg"],
                                note="Non-pregnant reference; interpret against gestational age")],
    "cortisol": [ReferenceRange("Cortisol (morning)", "ug/dL", 6.2, 19.4, aliases=["serum cortisol"])],
    "pth": [ReferenceRange("Parathyroid Hormone", "pg/mL", 15, 65, aliases=["pth", "intact pth"])],

    # ---------------- Tumour markers ----------------
    "ca_125": [ReferenceRange("CA 125", "U/mL", 0, 35, Gender.FEMALE, 0, 120, aliases=["ca-125", "ca125"])],
    "ca_15_3": [ReferenceRange("CA 15-3", "U/mL", 0, 31.3, aliases=["ca15-3"])],
    "ca_19_9": [ReferenceRange("CA 19-9", "U/mL", 0, 37, aliases=["ca19-9"])],
    "cea": [ReferenceRange("CEA", "ng/mL", 0, 3.0, aliases=["carcinoembryonic antigen"],
                           note="Up to 5.0 ng/mL in smokers")],
    "afp": [ReferenceRange("AFP", "ng/mL", 0, 10, aliases=["alpha fetoprotein"])],
    "psa": [ReferenceRange("PSA (Total)", "ng/mL", 0, 4.0, Gender.MALE, 0, 120,
                           aliases=["prostate specific antigen"])],
    "he4": [ReferenceRange("HE4", "pmol/L", 0, 70, Gender.FEMALE, 0, 120)],

    # ---------------- Urine ----------------
    "urine_ph": [ReferenceRange("Urine pH", "", 4.6, 8.0, aliases=["ph"])],
    "urine_specific_gravity": [ReferenceRange("Specific Gravity", "", 1.005, 1.030,
                                              aliases=["sp. gravity", "specific gravity"])],
    "urine_protein": [ReferenceRange("Urine Protein", "", None, None, aliases=["albumin urine", "protein urine"],
                                     note="Qualitative: Nil/Absent expected")],
    "urine_pus_cells": [ReferenceRange("Pus Cells", "/hpf", 0, 5, aliases=["wbc urine", "leucocytes urine"])],
    "urine_rbc": [ReferenceRange("RBC (Urine)", "/hpf", 0, 2, aliases=["red blood cells urine"])],
}

# Qualitative analytes: any value not in the expected set is flagged ABNORMAL.
QUALITATIVE_EXPECTED: Dict[str, List[str]] = {
    "urine_protein": ["nil", "absent", "negative", "trace"],
    "urine_sugar": ["nil", "absent", "negative"],
    "urine_ketones": ["nil", "absent", "negative"],
    "urine_blood": ["nil", "absent", "negative"],
    "urine_bile_salts": ["nil", "absent", "negative"],
    "urine_nitrite": ["negative", "absent", "nil"],
    "hbsag": ["non reactive", "nonreactive", "negative"],
    "hiv": ["non reactive", "nonreactive", "negative"],
    "hcv": ["non reactive", "nonreactive", "negative"],
    "vdrl": ["non reactive", "nonreactive", "negative"],
    "urine_pregnancy_test": ["negative"],
}

QUALITATIVE_ALIASES: Dict[str, List[str]] = {
    "urine_protein": ["urine protein", "protein", "albumin"],
    "urine_sugar": ["urine sugar", "sugar", "glucose urine"],
    "urine_ketones": ["ketones", "ketone bodies"],
    "urine_blood": ["blood", "occult blood"],
    "urine_bile_salts": ["bile salts", "bile pigments"],
    "urine_nitrite": ["nitrite", "nitrites"],
    "hbsag": ["hbsag", "hepatitis b surface antigen"],
    "hiv": ["hiv", "hiv i & ii", "hiv 1 & 2"],
    "hcv": ["hcv", "anti hcv", "hepatitis c"],
    "vdrl": ["vdrl", "rpr"],
    "urine_pregnancy_test": ["urine pregnancy test", "upt"],
}

# Unit normalisation: printed form -> canonical form used above.
UNIT_SYNONYMS: Dict[str, str] = {
    "gm/dl": "g/dL", "g/dl": "g/dL", "gm%": "g/dL", "g%": "g/dL",
    "mg/dl": "mg/dL", "mgs/dl": "mg/dL", "mg%": "mg/dL",
    "u/l": "U/L", "iu/l": "IU/L", "iu/ml": "IU/mL",
    "meq/l": "mEq/L", "mmol/l": "mmol/L",
    "ng/ml": "ng/mL", "pg/ml": "pg/mL", "ng/dl": "ng/dL",
    "ug/dl": "ug/dL", "mcg/dl": "ug/dL", "µg/dl": "ug/dL",
    "uiu/ml": "uIU/mL", "µiu/ml": "uIU/mL", "miu/ml": "mIU/mL",
    "mm/hr": "mm/hr", "mm/1st hr": "mm/hr", "mm 1st hour": "mm/hr",
    "cells/cumm": "cells/cumm", "cells/cu.mm": "cells/cumm", "/cumm": "cells/cumm",
    "cells/µl": "cells/cumm", "cells/ul": "cells/cumm", "/ul": "cells/cumm",
    "lakh/cumm": "lakh/cumm", "lakhs/cumm": "lakh/cumm",
    "million/cumm": "million/cumm", "mill/cumm": "million/cumm",
    "u/ml": "U/mL", "pmol/l": "pmol/L", "mg/l": "mg/L",
    "fl": "fL", "pg": "pg", "%": "%", "/hpf": "/hpf", "/ hpf": "/hpf",
}

# Convertible units: (from, to) -> multiplier.
UNIT_CONVERSIONS: Dict[tuple, float] = {
    ("cells/cumm", "thousand/cumm"): 0.001,
    ("thousand/cumm", "cells/cumm"): 1000.0,
    ("lakh/cumm", "thousand/cumm"): 100.0,
    ("thousand/cumm", "lakh/cumm"): 0.01,
    ("lakh/cumm", "cells/cumm"): 100000.0,
    ("cells/cumm", "lakh/cumm"): 0.00001,
}


def normalize_unit(unit: Optional[str]) -> str:
    if not unit:
        return ""
    cleaned = unit.strip().replace(" ", "").lower()
    return UNIT_SYNONYMS.get(cleaned, UNIT_SYNONYMS.get(unit.strip().lower(), unit.strip()))


# Specimen prefixes labs print before the analyte name ("S. Creatinine").
_SPECIMEN_PREFIXES = {"s", "serum", "plasma", "b", "blood", "urine", "p"}


def _clean(text: str) -> str:
    """One normaliser used for BOTH index building and lookup, so an alias
    written as "s. creatinine" is findable from "S. Creatinine"."""
    lowered = text.lower()
    for character in ".:,;/\\":
        lowered = lowered.replace(character, " ")
    lowered = " ".join(lowered.split())
    return lowered.strip(" -\u2013\u2014()")


def _alias_index() -> Dict[str, str]:
    index: Dict[str, str] = {}
    for key, ranges in REFERENCE_RANGES.items():
        index[_clean(key.replace("_", " "))] = key
        for entry in ranges:
            index[_clean(entry.analyte)] = key
            for alias in entry.aliases:
                index[_clean(alias)] = key
    for key, aliases in QUALITATIVE_ALIASES.items():
        index.setdefault(_clean(key.replace("_", " ")), key)
        for alias in aliases:
            index.setdefault(_clean(alias), key)
    return index


ALIAS_INDEX: Dict[str, str] = _alias_index()


def resolve_analyte(name: str) -> Optional[str]:
    """Map a printed analyte name onto a canonical key, or None if unknown."""
    cleaned = _clean(name)
    if not cleaned:
        return None

    def lookup(text: str) -> Optional[str]:
        if text in ALIAS_INDEX:
            return ALIAS_INDEX[text]
        # Longest-prefix match: "hemoglobin (hb) estimation" -> "hemoglobin"
        words = text.split()
        for size in range(len(words), 0, -1):
            candidate = " ".join(words[:size])
            if candidate in ALIAS_INDEX:
                return ALIAS_INDEX[candidate]
        return None

    direct = lookup(cleaned)
    if direct:
        return direct

    # Retry without a leading specimen prefix ("s creatinine" -> "creatinine").
    words = cleaned.split()
    while words and words[0] in _SPECIMEN_PREFIXES:
        words = words[1:]
        stripped = lookup(" ".join(words))
        if stripped:
            return stripped
    return None


def range_for(
    analyte_key: str, *, sex: Optional[Gender] = None, age: Optional[int] = None
) -> Optional[ReferenceRange]:
    """Best matching range for this patient, or None."""
    candidates = REFERENCE_RANGES.get(analyte_key)
    if not candidates:
        return None
    scored = []
    for entry in candidates:
        if entry.sex is not None and sex is not None and entry.sex != sex:
            continue
        if age is not None and not (entry.min_age <= age <= entry.max_age):
            continue
        score = (1 if entry.sex is not None else 0) + (1 if entry.max_age < 120 else 0)
        scored.append((score, entry))
    if not scored:
        # Fall back to a sex-agnostic entry rather than reporting nothing.
        generic = [e for e in candidates if e.sex is None]
        return generic[0] if generic else None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]
