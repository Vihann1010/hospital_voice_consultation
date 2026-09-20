"""The investigation catalog.

Held in code rather than the database: it is reference data that changes with
software releases, needs no per-row audit trail, and must be searchable without
a query. Orders denormalise the name and category at issue time, so revising
this file never rewrites history on a slip already printed.

Scope is what a district hospital in Kanpur can realistically order, weighted
towards orthopedics and gynecology.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.enums import Department, InvestigationCategory as Cat


@dataclass(frozen=True)
class Investigation:
    code: str
    name: str
    category: Cat
    aliases: List[str] = field(default_factory=list)
    specimen_or_site: Optional[str] = None
    preparation: Optional[str] = None
    turnaround: Optional[str] = None
    analytes: List[str] = field(default_factory=list)   # canonical reference-range keys
    departments: List[Department] = field(default_factory=list)  # empty = every department
    note: Optional[str] = None


@dataclass(frozen=True)
class Panel:
    code: str
    name: str
    description: str
    members: List[str]
    departments: List[Department] = field(default_factory=list)


C = Investigation

CATALOG: List[Investigation] = [
    # ------------------------------- BLOOD -------------------------------
    C("CBC", "Complete Blood Count", Cat.BLOOD, ["cbc", "hemogram", "haemogram", "blood count"],
      "Whole blood (EDTA)", None, "Same day",
      ["hemoglobin", "total_leukocyte_count", "platelet_count", "packed_cell_volume",
       "rbc_count", "mcv", "mch", "mchc"]),
    C("ESR", "Erythrocyte Sedimentation Rate", Cat.BLOOD, ["esr"], "Whole blood (EDTA)", None,
      "Same day", ["esr"]),
    C("CRP", "C-Reactive Protein", Cat.BLOOD, ["crp", "inflammatory marker"], "Serum", None,
      "Same day", ["crp"]),
    C("FBS", "Fasting Blood Sugar", Cat.BLOOD, ["fbs", "fasting glucose"], "Fluoride plasma",
      "8-12 hours fasting", "Same day", ["fasting_glucose"]),
    C("PPBS", "Post Prandial Blood Sugar", Cat.BLOOD, ["ppbs", "pp sugar"], "Fluoride plasma",
      "Sample 2 hours after a meal", "Same day", ["postprandial_glucose"]),
    C("RBS", "Random Blood Sugar", Cat.BLOOD, ["rbs"], "Fluoride plasma", None, "Same day",
      ["random_glucose"]),
    C("HBA1C", "HbA1c (Glycated Hemoglobin)", Cat.BLOOD, ["hba1c", "a1c"], "Whole blood (EDTA)",
      None, "Same day", ["hba1c"]),
    C("LFT", "Liver Function Test", Cat.BLOOD, ["lft", "liver profile"], "Serum",
      "Overnight fasting preferred", "Same day",
      ["total_bilirubin", "sgpt", "sgot", "alkaline_phosphatase", "total_protein", "albumin"]),
    C("KFT", "Kidney Function Test", Cat.BLOOD, ["kft", "rft", "renal profile"], "Serum", None,
      "Same day", ["urea", "creatinine", "uric_acid", "sodium", "potassium"]),
    C("LIPID", "Lipid Profile", Cat.BLOOD, ["lipid", "cholesterol"], "Serum", "12 hours fasting",
      "Same day", ["total_cholesterol", "ldl", "hdl", "triglycerides"]),
    C("ELECTRO", "Serum Electrolytes", Cat.BLOOD, ["electrolytes", "na k"], "Serum", None,
      "Same day", ["sodium", "potassium"]),
    C("CA_SERUM", "Serum Calcium", Cat.BLOOD, ["calcium"], "Serum", None, "Same day", ["calcium"]),
    C("PHOS", "Serum Phosphorus", Cat.BLOOD, ["phosphorus", "phosphate"], "Serum", None,
      "Same day", ["phosphorus"]),
    C("ALP", "Alkaline Phosphatase", Cat.BLOOD, ["alp"], "Serum", None, "Same day",
      ["alkaline_phosphatase"]),
    C("VITD", "Vitamin D (25-OH)", Cat.BLOOD, ["vitamin d", "vit d"], "Serum", None, "2-3 days",
      ["vitamin_d"]),
    C("VITB12", "Vitamin B12", Cat.BLOOD, ["b12"], "Serum", None, "2-3 days", ["vitamin_b12"]),
    C("IRON", "Iron Studies", Cat.BLOOD, ["iron profile", "ferritin"], "Serum", "Morning sample",
      "2 days", ["serum_iron", "ferritin"]),
    C("URIC", "Uric Acid", Cat.BLOOD, ["uric acid"], "Serum", None, "Same day", ["uric_acid"]),
    C("BLOODGRP", "Blood Group & Rh Typing", Cat.BLOOD, ["blood group", "abo"], "Whole blood",
      None, "Same day"),
    C("COAG", "Coagulation Profile (PT/INR, aPTT)", Cat.BLOOD, ["pt inr", "aptt", "coagulation"],
      "Citrated plasma", None, "Same day"),
    C("VIRAL", "Viral Markers (HBsAg, HCV, HIV)", Cat.BLOOD, ["viral markers", "hbsag", "hiv", "hcv"],
      "Serum", None, "Same day"),
    C("WIDAL", "Widal Test", Cat.BLOOD, ["widal", "typhoid"], "Serum", None, "Same day"),
    C("MP", "Malaria Parasite / Antigen", Cat.BLOOD, ["mp", "malaria"], "Whole blood", None,
      "Same day"),
    C("DENGUE", "Dengue NS1 / IgM / IgG", Cat.BLOOD, ["dengue"], "Serum", None, "Same day"),

    # ------------------------------- URINE -------------------------------
    C("URINE_RE", "Urine Routine & Microscopy", Cat.URINE, ["urine re", "urine routine", "ur m"],
      "Mid-stream urine", "Clean-catch mid-stream sample", "Same day",
      ["urine_ph", "urine_specific_gravity", "urine_protein", "urine_pus_cells", "urine_rbc"]),
    C("URINE_CS", "Urine Culture & Sensitivity", Cat.URINE, ["urine culture", "c s"],
      "Mid-stream urine", "Collect before starting antibiotics", "48-72 hours"),
    C("UPT", "Urine Pregnancy Test", Cat.URINE, ["upt", "pregnancy test"], "First morning urine",
      None, "Same day", departments=[Department.GYNECOLOGY]),
    C("URINE_ACR", "Urine Albumin/Creatinine Ratio", Cat.URINE, ["acr", "microalbumin"],
      "Spot urine", None, "Same day"),
    C("URINE_24H_PROT", "24-Hour Urinary Protein", Cat.URINE, ["24 hour protein"],
      "24-hour urine collection", "Discard first void, collect all urine for 24 hours", "2 days",
      departments=[Department.GYNECOLOGY]),

    # ------------------------------- X-RAY -------------------------------
    C("XR_CHEST", "X-Ray Chest PA", Cat.XRAY, ["chest x ray", "cxr"], "Chest", None, "Same day"),
    C("XR_KNEE", "X-Ray Knee (AP & Lateral)", Cat.XRAY, ["knee x ray"], "Knee",
      "Weight-bearing views if arthritis suspected", "Same day",
      departments=[Department.ORTHOPEDICS]),
    C("XR_LS_SPINE", "X-Ray Lumbosacral Spine", Cat.XRAY, ["ls spine", "lumbar x ray", "back x ray"],
      "Lumbosacral spine", None, "Same day", departments=[Department.ORTHOPEDICS]),
    C("XR_CERV_SPINE", "X-Ray Cervical Spine", Cat.XRAY, ["cervical spine x ray", "neck x ray"],
      "Cervical spine", None, "Same day", departments=[Department.ORTHOPEDICS]),
    C("XR_SHOULDER", "X-Ray Shoulder", Cat.XRAY, ["shoulder x ray"], "Shoulder", None, "Same day",
      departments=[Department.ORTHOPEDICS]),
    C("XR_HIP", "X-Ray Pelvis with Both Hips", Cat.XRAY, ["hip x ray", "pelvis x ray"],
      "Pelvis and hips", None, "Same day", departments=[Department.ORTHOPEDICS]),
    C("XR_WRIST", "X-Ray Wrist / Hand", Cat.XRAY, ["wrist x ray", "hand x ray"], "Wrist or hand",
      None, "Same day", departments=[Department.ORTHOPEDICS]),
    C("XR_ANKLE", "X-Ray Ankle / Foot", Cat.XRAY, ["ankle x ray", "foot x ray"], "Ankle or foot",
      None, "Same day", departments=[Department.ORTHOPEDICS]),
    C("XR_LONGBONE", "X-Ray Long Bone (specify limb)", Cat.XRAY, ["femur x ray", "tibia x ray"],
      "As specified", "Specify limb and side on the slip", "Same day",
      departments=[Department.ORTHOPEDICS]),

    # ------------------------------- MRI ---------------------------------
    C("MRI_LS_SPINE", "MRI Lumbosacral Spine", Cat.MRI, ["mri ls spine", "mri lumbar"],
      "Lumbosacral spine", "Remove all metal; declare implants or pacemaker", "1-2 days",
      departments=[Department.ORTHOPEDICS]),
    C("MRI_CERV_SPINE", "MRI Cervical Spine", Cat.MRI, ["mri cervical"], "Cervical spine",
      "Declare implants or pacemaker", "1-2 days", departments=[Department.ORTHOPEDICS]),
    C("MRI_KNEE", "MRI Knee", Cat.MRI, ["mri knee"], "Knee", "Declare implants", "1-2 days",
      departments=[Department.ORTHOPEDICS]),
    C("MRI_SHOULDER", "MRI Shoulder", Cat.MRI, ["mri shoulder"], "Shoulder", "Declare implants",
      "1-2 days", departments=[Department.ORTHOPEDICS]),
    C("MRI_PELVIS", "MRI Pelvis", Cat.MRI, ["mri pelvis"], "Pelvis",
      "Comfortably full bladder unless advised otherwise", "1-2 days"),
    C("MRI_BRAIN", "MRI Brain", Cat.MRI, ["mri brain", "mri head"], "Brain",
      "Declare implants or pacemaker", "1-2 days"),

    # -------------------------------- CT ---------------------------------
    C("CT_HEAD", "CT Head (Plain)", Cat.CT, ["ct brain", "ct head"], "Head", None, "Same day"),
    C("CT_SPINE", "CT Spine (specify level)", Cat.CT, ["ct spine"], "Spine",
      "Specify level on the slip", "Same day", departments=[Department.ORTHOPEDICS]),
    C("CT_ABDO_PELVIS", "CT Abdomen & Pelvis", Cat.CT, ["ct abdomen", "ct pelvis"],
      "Abdomen and pelvis", "4-6 hours fasting; contrast may be used — check renal function",
      "Same day"),
    C("CT_KUB", "CT KUB (Stone Protocol)", Cat.CT, ["ct kub", "stone protocol"],
      "Kidneys, ureters, bladder", "No contrast required", "Same day"),
    C("CT_CHEST", "CT Chest", Cat.CT, ["ct thorax", "hrct"], "Chest", None, "Same day"),
    C("CT_3D_RECON", "CT with 3D Reconstruction (fracture)", Cat.CT, ["3d ct", "fracture ct"],
      "As specified", "Specify the region and side", "1 day",
      departments=[Department.ORTHOPEDICS]),

    # ---------------------------- ULTRASOUND ------------------------------
    C("USG_ABDO", "Ultrasound Whole Abdomen", Cat.ULTRASOUND, ["usg abdomen", "sonography abdomen"],
      "Abdomen", "6 hours fasting; full bladder", "Same day"),
    C("USG_PELVIS", "Ultrasound Pelvis", Cat.ULTRASOUND, ["usg pelvis"], "Pelvis",
      "Full bladder required", "Same day", departments=[Department.GYNECOLOGY]),
    C("USG_TVS", "Transvaginal Ultrasound (TVS)", Cat.ULTRASOUND, ["tvs", "transvaginal"],
      "Pelvis (transvaginal)", "Empty bladder", "Same day", departments=[Department.GYNECOLOGY]),
    C("USG_OBS", "Obstetric Ultrasound", Cat.ULTRASOUND, ["obstetric scan", "pregnancy scan"],
      "Gravid uterus", "Specify gestational age on the slip", "Same day",
      departments=[Department.GYNECOLOGY]),
    C("USG_NT", "NT/NB Scan (11-13 weeks)", Cat.ULTRASOUND, ["nt scan", "nuchal translucency"],
      "Gravid uterus", "Book between 11 and 13 weeks 6 days", "Same day",
      departments=[Department.GYNECOLOGY]),
    C("USG_ANOMALY", "Anomaly Scan (18-22 weeks)", Cat.ULTRASOUND, ["anomaly scan", "tifa"],
      "Gravid uterus", "Book between 18 and 22 weeks", "Same day",
      departments=[Department.GYNECOLOGY]),
    C("USG_DOPPLER_OBS", "Obstetric Doppler", Cat.ULTRASOUND, ["fetal doppler"], "Gravid uterus",
      None, "Same day", departments=[Department.GYNECOLOGY]),
    C("USG_FOLLICLE", "Follicular Monitoring", Cat.ULTRASOUND, ["follicular study"], "Pelvis",
      "Serial scans from day 9 of the cycle", "Same day", departments=[Department.GYNECOLOGY]),
    C("USG_BREAST", "Ultrasound Breast", Cat.ULTRASOUND, ["breast usg"], "Breast", None,
      "Same day", departments=[Department.GYNECOLOGY]),
    C("USG_MSK", "Musculoskeletal Ultrasound", Cat.ULTRASOUND, ["msk usg", "soft tissue usg"],
      "As specified", "Specify the joint or region", "Same day",
      departments=[Department.ORTHOPEDICS]),
    C("USG_DOPPLER_LIMB", "Venous Doppler Limb", Cat.ULTRASOUND, ["dvt doppler", "venous doppler"],
      "Limb", "Specify limb and side", "Same day", departments=[Department.ORTHOPEDICS]),

    # ------------------------------- DEXA --------------------------------
    C("DEXA_SPINE_HIP", "DEXA Scan (Spine & Hip)", Cat.DEXA, ["dexa", "bmd", "bone density"],
      "Lumbar spine and hip", "Avoid calcium supplements 24 hours before", "Same day",
      note="Reports T-score and Z-score"),
    C("DEXA_FOREARM", "DEXA Scan (Forearm)", Cat.DEXA, ["forearm bmd"], "Forearm", None,
      "Same day"),
    C("DEXA_BODY", "DEXA Body Composition", Cat.DEXA, ["body composition"], "Whole body", None,
      "Same day"),

    # ---------------------------- ORTHOPEDIC ------------------------------
    C("ORTHO_NCV", "Nerve Conduction Velocity (NCV)", Cat.ORTHOPEDIC, ["ncv", "nerve conduction"],
      "As specified", "Specify limb and nerve", "1-2 days", departments=[Department.ORTHOPEDICS]),
    C("ORTHO_EMG", "Electromyography (EMG)", Cat.ORTHOPEDIC, ["emg"], "As specified", None,
      "1-2 days", departments=[Department.ORTHOPEDICS]),
    C("ORTHO_RA", "Rheumatoid Factor (RA Factor)", Cat.ORTHOPEDIC, ["ra factor", "rf"], "Serum",
      None, "1 day", ["ra_factor"], departments=[Department.ORTHOPEDICS]),
    C("ORTHO_ACCP", "Anti-CCP Antibody", Cat.ORTHOPEDIC, ["anti ccp", "acpa"], "Serum", None,
      "2-3 days", ["anti_ccp"], departments=[Department.ORTHOPEDICS]),
    C("ORTHO_HLAB27", "HLA-B27", Cat.ORTHOPEDIC, ["hla b27"], "Whole blood (EDTA)", None,
      "3-5 days", departments=[Department.ORTHOPEDICS]),
    C("ORTHO_ANA", "ANA (Antinuclear Antibody)", Cat.ORTHOPEDIC, ["ana", "antinuclear"], "Serum",
      None, "2-3 days", departments=[Department.ORTHOPEDICS]),
    C("ORTHO_SYNOVIAL", "Synovial Fluid Analysis", Cat.ORTHOPEDIC, ["joint fluid", "synovial"],
      "Joint aspirate", "Aspirate under aseptic precautions", "1-2 days",
      departments=[Department.ORTHOPEDICS]),
    C("ORTHO_BONE_SCAN", "Bone Scan (Technetium)", Cat.ORTHOPEDIC, ["bone scan", "scintigraphy"],
      "Whole body", "Hydration advised after injection", "1-2 days",
      departments=[Department.ORTHOPEDICS]),
    C("ORTHO_BONE_PROFILE", "Bone Profile (Ca, PO4, ALP, Vit D, PTH)", Cat.ORTHOPEDIC,
      ["bone profile", "metabolic bone"], "Serum", "Morning fasting sample", "2-3 days",
      ["calcium", "phosphorus", "alkaline_phosphatase", "vitamin_d", "pth"],
      departments=[Department.ORTHOPEDICS]),

    # ---------------------------- GYNECOLOGY ------------------------------
    C("GYN_PAP", "Pap Smear (Cervical Cytology)", Cat.GYNECOLOGY, ["pap", "cervical smear"],
      "Cervical smear", "Avoid during menstruation; no intercourse 48 hours before", "3-5 days",
      departments=[Department.GYNECOLOGY]),
    C("GYN_HPV", "HPV DNA Test", Cat.GYNECOLOGY, ["hpv"], "Cervical sample", None, "5-7 days",
      departments=[Department.GYNECOLOGY]),
    C("GYN_HVS", "High Vaginal Swab C/S", Cat.GYNECOLOGY, ["hvs", "vaginal swab"], "Vaginal swab",
      "Collect before starting antibiotics", "48-72 hours", departments=[Department.GYNECOLOGY]),
    C("GYN_ENDO_BIOPSY", "Endometrial Biopsy (Histopathology)", Cat.GYNECOLOGY,
      ["endometrial biopsy", "d c biopsy"], "Endometrial tissue", None, "5-7 days",
      departments=[Department.GYNECOLOGY]),
    C("GYN_HSG", "Hysterosalpingography (HSG)", Cat.GYNECOLOGY, ["hsg", "tubal patency"],
      "Uterus and tubes", "Perform in the follicular phase, after menses stop", "1-2 days",
      departments=[Department.GYNECOLOGY]),
    C("GYN_MAMMO", "Mammography", Cat.GYNECOLOGY, ["mammogram"], "Both breasts",
      "Avoid deodorant or talc on the day", "1-2 days", departments=[Department.GYNECOLOGY]),
    C("GYN_OGTT", "OGTT (75g, Pregnancy)", Cat.GYNECOLOGY, ["ogtt", "gtt", "gdm screening"],
      "Plasma glucose series", "Overnight fasting; remain seated through the test", "Same day",
      ["fasting_glucose", "postprandial_glucose"], departments=[Department.GYNECOLOGY]),
    C("GYN_ANTENATAL", "Antenatal Profile", Cat.GYNECOLOGY, ["antenatal profile", "anc profile"],
      "Blood and urine", "First-visit screening panel", "1-2 days",
      ["hemoglobin", "fasting_glucose"], departments=[Department.GYNECOLOGY]),

    # ----------------------------- HORMONAL -------------------------------
    C("HORM_TFT", "Thyroid Profile (T3, T4, TSH)", Cat.HORMONAL, ["tft", "thyroid profile"],
      "Serum", "Morning sample preferred", "Same day", ["t3", "t4", "tsh"]),
    C("HORM_FT34", "Free T3 & Free T4", Cat.HORMONAL, ["ft3 ft4", "free thyroid"], "Serum", None,
      "1 day", ["free_t3", "free_t4"]),
    C("HORM_PROLACTIN", "Serum Prolactin", Cat.HORMONAL, ["prolactin", "prl"], "Serum",
      "Morning sample, rested 30 minutes, avoid breast stimulation", "1 day", ["prolactin"]),
    C("HORM_FSH_LH", "FSH & LH", Cat.HORMONAL, ["fsh lh", "gonadotropins"], "Serum",
      "Day 2-3 of the cycle in women", "1 day", ["fsh", "lh"],
      departments=[Department.GYNECOLOGY]),
    C("HORM_ESTRADIOL", "Estradiol (E2)", Cat.HORMONAL, ["estradiol", "e2"], "Serum",
      "State cycle day on the slip", "1 day", ["estradiol"],
      departments=[Department.GYNECOLOGY]),
    C("HORM_PROGESTERONE", "Serum Progesterone", Cat.HORMONAL, ["progesterone"], "Serum",
      "Day 21 of the cycle for ovulation confirmation", "1 day", ["progesterone"],
      departments=[Department.GYNECOLOGY]),
    C("HORM_TESTOSTERONE", "Total Testosterone", Cat.HORMONAL, ["testosterone"], "Serum",
      "Morning sample", "1-2 days", ["testosterone"]),
    C("HORM_AMH", "Anti-Mullerian Hormone (AMH)", Cat.HORMONAL, ["amh", "ovarian reserve"],
      "Serum", "Any day of the cycle", "3-5 days", ["amh"],
      departments=[Department.GYNECOLOGY]),
    C("HORM_BHCG", "Beta hCG (Quantitative)", Cat.HORMONAL, ["beta hcg", "b hcg"], "Serum", None,
      "Same day", ["beta_hcg"], departments=[Department.GYNECOLOGY]),
    C("HORM_CORTISOL", "Serum Cortisol (Morning)", Cat.HORMONAL, ["cortisol"], "Serum",
      "Sample between 8 and 9 AM", "1-2 days", ["cortisol"]),
    C("HORM_PTH", "Parathyroid Hormone (PTH)", Cat.HORMONAL, ["pth"], "Serum", None, "2-3 days",
      ["pth"], departments=[Department.ORTHOPEDICS]),
    C("HORM_INSULIN", "Fasting Insulin", Cat.HORMONAL, ["insulin"], "Serum", "8-12 hours fasting",
      "2-3 days"),

    # -------------------------- TUMOUR MARKERS ----------------------------
    C("TM_CA125", "CA 125", Cat.TUMOR_MARKERS, ["ca 125", "ca125"], "Serum", None, "2-3 days",
      ["ca_125"], departments=[Department.GYNECOLOGY]),
    C("TM_CA153", "CA 15-3", Cat.TUMOR_MARKERS, ["ca 15 3"], "Serum", None, "2-3 days",
      ["ca_15_3"], departments=[Department.GYNECOLOGY]),
    C("TM_CA199", "CA 19-9", Cat.TUMOR_MARKERS, ["ca 19 9"], "Serum", None, "2-3 days", ["ca_19_9"]),
    C("TM_CEA", "CEA", Cat.TUMOR_MARKERS, ["cea"], "Serum", None, "2-3 days", ["cea"]),
    C("TM_AFP", "Alpha Fetoprotein (AFP)", Cat.TUMOR_MARKERS, ["afp"], "Serum", None, "2-3 days",
      ["afp"]),
    C("TM_PSA", "PSA (Total)", Cat.TUMOR_MARKERS, ["psa"], "Serum",
      "Avoid ejaculation or cycling 48 hours before", "2-3 days", ["psa"]),
    C("TM_HE4", "HE4", Cat.TUMOR_MARKERS, ["he4"], "Serum", None, "3-5 days", ["he4"],
      departments=[Department.GYNECOLOGY]),
    C("TM_LDH", "LDH", Cat.TUMOR_MARKERS, ["ldh", "lactate dehydrogenase"], "Serum", None,
      "Same day"),
]

PANELS: List[Panel] = [
    Panel("PANEL_BASIC", "Basic Screening", "Baseline blood work for a new patient",
          ["CBC", "FBS", "URINE_RE"]),
    Panel("PANEL_METABOLIC", "Metabolic Workup", "Diabetes, lipids, liver and kidney together",
          ["HBA1C", "FBS", "LIPID", "LFT", "KFT"]),
    Panel("PANEL_PREOP", "Pre-Operative Workup", "Standard clearance before surgery",
          ["CBC", "COAG", "KFT", "BLOODGRP", "VIRAL", "XR_CHEST"]),
    Panel("PANEL_ANEMIA", "Anemia Workup", "Establish the type and cause of anemia",
          ["CBC", "IRON", "VITB12", "ESR"]),
    Panel("PANEL_BONE", "Bone Health Workup", "Osteoporosis and metabolic bone disease",
          ["ORTHO_BONE_PROFILE", "DEXA_SPINE_HIP", "HORM_PTH"],
          departments=[Department.ORTHOPEDICS]),
    Panel("PANEL_ARTHRITIS", "Inflammatory Arthritis Workup",
          "Distinguish inflammatory from degenerative joint disease",
          ["CBC", "ESR", "CRP", "ORTHO_RA", "ORTHO_ACCP", "URIC"],
          departments=[Department.ORTHOPEDICS]),
    Panel("PANEL_BACKPAIN", "Back Pain Workup", "Structural and inflammatory causes of back pain",
          ["XR_LS_SPINE", "ESR", "CRP", "VITD"], departments=[Department.ORTHOPEDICS]),
    Panel("PANEL_ANC_FIRST", "Antenatal First Visit", "Booking-visit screening",
          ["CBC", "BLOODGRP", "VIRAL", "URINE_RE", "HORM_TFT", "FBS", "USG_OBS"],
          departments=[Department.GYNECOLOGY]),
    Panel("PANEL_PCOS", "PCOS Workup", "Hormonal and metabolic assessment for PCOS",
          ["HORM_FSH_LH", "HORM_PROLACTIN", "HORM_TFT", "HORM_TESTOSTERONE", "HORM_INSULIN",
           "USG_PELVIS"], departments=[Department.GYNECOLOGY]),
    Panel("PANEL_INFERTILITY", "Infertility Workup", "Baseline female infertility assessment",
          ["HORM_FSH_LH", "HORM_AMH", "HORM_PROLACTIN", "HORM_TFT", "USG_TVS", "GYN_HSG"],
          departments=[Department.GYNECOLOGY]),
    Panel("PANEL_AUB", "Abnormal Uterine Bleeding", "Common causes of irregular or heavy bleeding",
          ["CBC", "HORM_TFT", "HORM_PROLACTIN", "USG_TVS", "GYN_ENDO_BIOPSY"],
          departments=[Department.GYNECOLOGY]),
    Panel("PANEL_MENOPAUSE", "Menopausal Health Check", "Bone and metabolic health after menopause",
          ["DEXA_SPINE_HIP", "VITD", "CA_SERUM", "LIPID", "HORM_TFT", "GYN_MAMMO"],
          departments=[Department.GYNECOLOGY]),
]

CATALOG_BY_CODE: Dict[str, Investigation] = {item.code: item for item in CATALOG}
PANELS_BY_CODE: Dict[str, Panel] = {panel.code: panel for panel in PANELS}

CATEGORY_LABELS: Dict[str, str] = {
    Cat.BLOOD.value: "Blood",
    Cat.URINE.value: "Urine",
    Cat.XRAY.value: "X-Ray",
    Cat.MRI.value: "MRI",
    Cat.CT.value: "CT",
    Cat.ULTRASOUND.value: "Ultrasound",
    Cat.DEXA.value: "DEXA",
    Cat.ORTHOPEDIC.value: "Orthopedic",
    Cat.GYNECOLOGY.value: "Gynecology",
    Cat.HORMONAL.value: "Hormonal",
    Cat.TUMOR_MARKERS.value: "Tumor Markers",
}


def _haystack(item: Investigation) -> str:
    return " ".join(
        [item.code.lower(), item.name.lower(), *[a.lower() for a in item.aliases],
         (item.specimen_or_site or "").lower()]
    )


_SEARCH_INDEX: Dict[str, str] = {item.code: _haystack(item) for item in CATALOG}


def search(
    query: Optional[str] = None,
    *,
    category: Optional[Cat] = None,
    department: Optional[Department] = None,
    limit: int = 200,
) -> List[Investigation]:
    """Rank catalog matches: exact code, then name prefix, then substring."""
    results = CATALOG
    if category is not None:
        results = [item for item in results if item.category == category]
    if department is not None:
        results = [item for item in results
                   if not item.departments or department in item.departments]
    if not query or not query.strip():
        return sorted(results, key=lambda item: item.name)[:limit]

    term = " ".join(query.lower().split())
    scored = []
    for item in results:
        haystack = _SEARCH_INDEX[item.code]
        name = item.name.lower()
        if item.code.lower() == term:
            score = 0
        elif name.startswith(term):
            score = 1
        elif any(alias.lower().startswith(term) for alias in item.aliases):
            score = 2
        elif term in haystack:
            score = 3
        elif all(word in haystack for word in term.split()):
            score = 4
        else:
            continue
        scored.append((score, item.name, item))
    scored.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in scored[:limit]]


def get(code: str) -> Optional[Investigation]:
    return CATALOG_BY_CODE.get(code)


def expand_codes(codes: List[str]) -> List[Investigation]:
    """Resolve a mixed list of investigation and panel codes, de-duplicated."""
    resolved: List[Investigation] = []
    seen = set()
    for code in codes:
        panel = PANELS_BY_CODE.get(code)
        members = panel.members if panel else [code]
        for member in members:
            item = CATALOG_BY_CODE.get(member)
            if item and item.code not in seen:
                seen.add(item.code)
                resolved.append(item)
    return resolved
