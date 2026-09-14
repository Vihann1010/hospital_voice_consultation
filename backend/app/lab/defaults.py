"""A starting laboratory: the tests a hospital of this size runs, and the short
lists the bench picks from.

**The starter ranges are not this laboratory's ranges.** Numeric parameters
take their ranges from the platform's built-in table (the one outside reports
are compared against), because a list with no ranges at all would flag
nothing. Every test is loaded unreviewed, and an unreviewed test cannot be
verified: the pathologist reads each range against the analyser and reagent
kit actually in use and marks the test reviewed before a single report goes
out. Parameters with no built-in range (the differential count, the
coagulation profile) are loaded with none; they print unflagged until the
pathologist adds one.

No methods are assigned and no prices are set. Both belong to the hospital.
"""
from typing import Any, Dict, List, Optional

from app.investigations.reference_ranges import REFERENCE_RANGES

GROUPS = ["Haematology", "Biochemistry", "Clinical pathology", "Serology", "Hormones",
          "Tumour markers", "Coagulation", "Microbiology"]

UNITS = ["g/dL", "cells/cumm", "lakh/cumm", "million/cumm", "%", "fL", "pg", "mm/hr", "mg/dL",
         "mg/L", "U/L", "IU/mL", "mEq/L", "mmol/L", "ng/mL", "ng/dL", "pg/mL", "ug/dL", "uIU/mL",
         "mIU/mL", "U/mL", "pmol/L", "seconds", "/hpf"]

SPECIMENS = ["Whole blood (EDTA)", "Serum", "Fluoride plasma", "Citrated plasma", "Urine",
             "Mid-stream urine", "Pus", "Blood (culture bottle)", "High vaginal swab", "Sputum",
             "Wound swab", "Synovial fluid", "Stool"]

METHODS = ["Automated analyser", "Manual", "Microscopy", "Immunochromatography", "ELISA",
           "CLIA", "Slide agglutination", "Tube agglutination", "Kirby-Bauer disc diffusion", "MIC"]

ORGANISMS = ["Escherichia coli", "Klebsiella pneumoniae", "Pseudomonas aeruginosa",
             "Staphylococcus aureus", "Coagulase-negative Staphylococcus", "Enterococcus faecalis",
             "Proteus mirabilis", "Acinetobacter baumannii", "Enterobacter species",
             "Citrobacter species", "Streptococcus species", "Candida species"]

ANTIBIOTICS = [
    ("Ampicillin", "Penicillins"), ("Amoxicillin-clavulanate", "Penicillins"),
    ("Piperacillin-tazobactam", "Penicillins"), ("Penicillin", "Penicillins"),
    ("Oxacillin / Cefoxitin screen", "Penicillins"),
    ("Cefazolin", "Cephalosporins"), ("Cefuroxime", "Cephalosporins"), ("Cefixime", "Cephalosporins"),
    ("Cefotaxime", "Cephalosporins"), ("Ceftriaxone", "Cephalosporins"),
    ("Ceftazidime", "Cephalosporins"), ("Cefepime", "Cephalosporins"),
    ("Cefoperazone-sulbactam", "Cephalosporins"),
    ("Ertapenem", "Carbapenems"), ("Imipenem", "Carbapenems"), ("Meropenem", "Carbapenems"),
    ("Amikacin", "Aminoglycosides"), ("Gentamicin", "Aminoglycosides"),
    ("Ciprofloxacin", "Fluoroquinolones"), ("Levofloxacin", "Fluoroquinolones"),
    ("Ofloxacin", "Fluoroquinolones"), ("Norfloxacin", "Fluoroquinolones"),
    ("Azithromycin", "Macrolides"), ("Erythromycin", "Macrolides"),
    ("Clindamycin", "Lincosamides"), ("Doxycycline", "Tetracyclines"),
    ("Tetracycline", "Tetracyclines"), ("Tigecycline", "Tetracyclines"),
    ("Cotrimoxazole", "Folate pathway inhibitors"), ("Nitrofurantoin", "Urinary agents"),
    ("Fosfomycin", "Urinary agents"), ("Vancomycin", "Glycopeptides"),
    ("Teicoplanin", "Glycopeptides"), ("Linezolid", "Oxazolidinones"), ("Colistin", "Polymyxins"),
]


def starter_ranges(analyte_key: str) -> List[Dict[str, Any]]:
    """The built-in table's ranges for an analyte, in the lab's own shape."""
    out = []
    for entry in REFERENCE_RANGES.get(analyte_key, []):
        if entry.low is None and entry.high is None:
            continue
        out.append({
            "sex": entry.sex.value if entry.sex is not None else None,
            "min_age": entry.min_age, "max_age": entry.max_age,
            "low": entry.low, "high": entry.high,
            "critical_low": entry.critical_low, "critical_high": entry.critical_high,
        })
    return out


def _unit(analyte_key: str) -> Optional[str]:
    entries = REFERENCE_RANGES.get(analyte_key) or []
    return entries[0].unit or None if entries else None


def num(name: str, key: Optional[str] = None, unit: Optional[str] = None) -> Dict[str, Any]:
    return {"name": name, "analyte_key": key, "result_type": "numeric",
            "unit": unit if unit is not None else (_unit(key) if key else None),
            "ranges": starter_ranges(key) if key else []}


def choice(name: str, choices: List[str], normal: Optional[List[str]] = None,
           key: Optional[str] = None) -> Dict[str, Any]:
    return {"name": name, "analyte_key": key, "result_type": "choice", "choices": choices,
            "normal_values": normal or []}


def text(name: str, key: Optional[str] = None) -> Dict[str, Any]:
    return {"name": name, "analyte_key": key, "result_type": "text"}


def heading(name: str) -> Dict[str, Any]:
    return {"name": name, "result_type": "heading", "print_default": True}


GRADE = ["Nil", "Trace", "+", "++", "+++", "++++"]
REACTIVE = ["Non-reactive", "Reactive"]
POS_NEG = ["Negative", "Positive"]

# (code, name, group, specimen, catalog code, service code, parameters, culture, turnaround hours)
TESTS = [
    ("CBC", "Complete Blood Count", "Haematology", "Whole blood (EDTA)", "CBC", "INV-CBC", [
        num("Haemoglobin", "hemoglobin"), num("Total leucocyte count", "total_leukocyte_count"),
        heading("Differential leucocyte count"),
        num("Neutrophils", unit="%"), num("Lymphocytes", unit="%"), num("Monocytes", unit="%"),
        num("Eosinophils", unit="%"), num("Basophils", unit="%"),
        num("Platelet count", "platelet_count"), num("Packed cell volume", "packed_cell_volume"),
        num("RBC count", "rbc_count"), num("MCV", "mcv"), num("MCH", "mch"), num("MCHC", "mchc"),
    ], False, 6),
    ("ESR", "Erythrocyte Sedimentation Rate", "Haematology", "Whole blood (EDTA)", "ESR", None,
     [num("ESR", "esr")], False, 6),
    ("BLOODGRP", "Blood Group & Rh Typing", "Haematology", "Whole blood (EDTA)", "BLOODGRP", None,
     [choice("ABO group", ["A", "B", "AB", "O"]), choice("Rh (D)", ["Positive", "Negative"])], False, 2),
    ("MP", "Malaria Parasite / Antigen", "Haematology", "Whole blood (EDTA)", "MP", None,
     [choice("Malaria parasite", ["Not seen", "Seen"], ["Not seen"]), text("Species")], False, 4),
    ("COAG", "Coagulation Profile (PT/INR, aPTT)", "Coagulation", "Citrated plasma", "COAG", None, [
        num("Prothrombin time", unit="seconds"), num("PT control", unit="seconds"), num("INR", unit=""),
        num("aPTT", unit="seconds"), num("aPTT control", unit="seconds"),
    ], False, 6),
    ("FBS", "Fasting Blood Sugar", "Biochemistry", "Fluoride plasma", "FBS", None,
     [num("Fasting blood sugar", "fasting_glucose")], False, 4),
    ("PPBS", "Post Prandial Blood Sugar", "Biochemistry", "Fluoride plasma", "PPBS", None,
     [num("Post prandial blood sugar", "postprandial_glucose")], False, 4),
    ("RBS", "Random Blood Sugar", "Biochemistry", "Fluoride plasma", "RBS", "INV-RBS",
     [num("Random blood sugar", "random_glucose")], False, 2),
    ("HBA1C", "HbA1c (Glycated Haemoglobin)", "Biochemistry", "Whole blood (EDTA)", "HBA1C", None,
     [num("HbA1c", "hba1c")], False, 24),
    ("LFT", "Liver Function Test", "Biochemistry", "Serum", "LFT", None, [
        num("Total bilirubin", "total_bilirubin"), num("SGPT (ALT)", "sgpt"), num("SGOT (AST)", "sgot"),
        num("Alkaline phosphatase", "alkaline_phosphatase"), num("Total protein", "total_protein"),
        num("Albumin", "albumin"),
    ], False, 8),
    ("KFT", "Kidney Function Test", "Biochemistry", "Serum", "KFT", None, [
        num("Blood urea", "urea"), num("Serum creatinine", "creatinine"), num("Uric acid", "uric_acid"),
        num("Sodium", "sodium"), num("Potassium", "potassium"),
    ], False, 8),
    ("LIPID", "Lipid Profile", "Biochemistry", "Serum", "LIPID", None, [
        num("Total cholesterol", "total_cholesterol"), num("Triglycerides", "triglycerides"),
        num("HDL cholesterol", "hdl"), num("LDL cholesterol", "ldl"),
    ], False, 24),
    ("ELECTRO", "Serum Electrolytes", "Biochemistry", "Serum", "ELECTRO", None,
     [num("Sodium", "sodium"), num("Potassium", "potassium")], False, 4),
    ("CA_SERUM", "Serum Calcium", "Biochemistry", "Serum", "CA_SERUM", None,
     [num("Serum calcium", "calcium")], False, 8),
    ("PHOS", "Serum Phosphorus", "Biochemistry", "Serum", "PHOS", None,
     [num("Serum phosphorus", "phosphorus")], False, 8),
    ("URIC", "Uric Acid", "Biochemistry", "Serum", "URIC", None, [num("Uric acid", "uric_acid")], False, 8),
    ("CRP", "C-Reactive Protein", "Serology", "Serum", "CRP", None, [num("CRP", "crp")], False, 6),
    ("VITD", "Vitamin D (25-OH)", "Biochemistry", "Serum", "VITD", None,
     [num("25-OH Vitamin D", "vitamin_d")], False, 72),
    ("VITB12", "Vitamin B12", "Biochemistry", "Serum", "VITB12", None,
     [num("Vitamin B12", "vitamin_b12")], False, 72),
    ("IRON", "Iron Studies", "Biochemistry", "Serum", "IRON", None,
     [num("Serum iron", "serum_iron"), num("Ferritin", "ferritin")], False, 48),
    ("HORM_TFT", "Thyroid Profile (T3, T4, TSH)", "Hormones", "Serum", "HORM_TFT", None,
     [num("T3 (total)", "t3"), num("T4 (total)", "t4"), num("TSH", "tsh")], False, 24),
    ("HORM_PROLACTIN", "Serum Prolactin", "Hormones", "Serum", "HORM_PROLACTIN", None,
     [num("Prolactin", "prolactin")], False, 24),
    ("HORM_BHCG", "Beta hCG (Quantitative)", "Hormones", "Serum", "HORM_BHCG", None,
     [num("Beta hCG", "beta_hcg")], False, 24),
    ("ORTHO_RA", "Rheumatoid Factor (RA Factor)", "Serology", "Serum", "ORTHO_RA", None,
     [num("Rheumatoid factor", "ra_factor")], False, 24),
    ("VIRAL", "Viral Markers (HBsAg, HCV, HIV)", "Serology", "Serum", "VIRAL", None, [
        choice("HBsAg", REACTIVE, ["Non-reactive"], "hbsag"),
        choice("Anti-HCV", REACTIVE, ["Non-reactive"], "hcv"),
        choice("HIV I & II", REACTIVE, ["Non-reactive"], "hiv"),
    ], False, 6),
    ("WIDAL", "Widal Test", "Serology", "Serum", "WIDAL", None, [
        text("S. Typhi O"), text("S. Typhi H"), text("S. Paratyphi AH"), text("S. Paratyphi BH"),
    ], False, 24),
    ("DENGUE", "Dengue NS1 / IgM / IgG", "Serology", "Serum", "DENGUE", None, [
        choice("NS1 antigen", POS_NEG, ["Negative"]), choice("IgM antibody", POS_NEG, ["Negative"]),
        choice("IgG antibody", POS_NEG, ["Negative"]),
    ], False, 6),
    ("URINE_RE", "Urine Routine & Microscopy", "Clinical pathology", "Mid-stream urine", "URINE_RE",
     "INV-URINE", [
        heading("Physical examination"), text("Colour"), text("Appearance"),
        num("pH", "urine_ph"), num("Specific gravity", "urine_specific_gravity"),
        heading("Chemical examination"),
        choice("Protein", GRADE, ["Nil", "Trace"], "urine_protein"),
        choice("Sugar", GRADE, ["Nil"], "urine_sugar"),
        choice("Ketone bodies", POS_NEG, ["Negative"], "urine_ketones"),
        heading("Microscopic examination"),
        text("Pus cells (/hpf)"), text("RBC (/hpf)"), text("Epithelial cells (/hpf)"),
        text("Casts"), text("Crystals"),
    ], False, 4),
    ("UPT", "Urine Pregnancy Test", "Clinical pathology", "Urine", "UPT", None,
     [choice("Urine pregnancy test", POS_NEG)], False, 1),
    ("URINE_CS", "Urine Culture & Sensitivity", "Microbiology", "Mid-stream urine", "URINE_CS", None,
     [], True, 72),
    ("GYN_HVS", "High Vaginal Swab C/S", "Microbiology", "High vaginal swab", "GYN_HVS", None, [], True, 72),
    ("PUS_CS", "Pus Culture & Sensitivity", "Microbiology", "Pus", None, None, [], True, 72),
    ("BLOOD_CS", "Blood Culture & Sensitivity", "Microbiology", "Blood (culture bottle)", None, None,
     [], True, 120),
]
