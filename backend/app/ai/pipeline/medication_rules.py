"""Deterministic medication safety rules.

Duplicate therapy and allergy conflicts are decided by rules, not by a model,
because these are exact-match problems where a language model's uncertainty
buys nothing. Brand names common in Indian practice are mapped to their active
ingredients, so "Dolo 650" and "Crocin" are recognised as the same drug.

Anything these rules cannot decide (true pharmacodynamic interactions) is left
to the LLM stage, and every alert carries `detected_by` so the doctor can see
which is which.
"""
import re
from typing import Dict, Iterable, List, Set

from app.ai.pipeline.schemas import MedicationAlert

# Brand / common name -> active ingredient(s). Lowercase keys.
BRAND_INGREDIENTS: Dict[str, List[str]] = {
    "crocin": ["paracetamol"],
    "dolo": ["paracetamol"],
    "calpol": ["paracetamol"],
    "pacimol": ["paracetamol"],
    "paracip": ["paracetamol"],
    "tylenol": ["paracetamol"],
    "acetaminophen": ["paracetamol"],
    "combiflam": ["ibuprofen", "paracetamol"],
    "brufen": ["ibuprofen"],
    "ibugesic": ["ibuprofen"],
    "zerodol": ["aceclofenac"],
    "hifenac": ["aceclofenac"],
    "voveran": ["diclofenac"],
    "dicloran": ["diclofenac"],
    "naprosyn": ["naproxen"],
    "etoshine": ["etoricoxib"],
    "nucoxia": ["etoricoxib"],
    "disprin": ["aspirin"],
    "ecosprin": ["aspirin"],
    "pan": ["pantoprazole"],
    "pantop": ["pantoprazole"],
    "pantocid": ["pantoprazole"],
    "omez": ["omeprazole"],
    "rablet": ["rabeprazole"],
    "razo": ["rabeprazole"],
    "augmentin": ["amoxicillin", "clavulanic acid"],
    "clavam": ["amoxicillin", "clavulanic acid"],
    "mox": ["amoxicillin"],
    "amoxyclav": ["amoxicillin", "clavulanic acid"],
    "azithral": ["azithromycin"],
    "azee": ["azithromycin"],
    "taxim": ["cefixime"],
    "cifran": ["ciprofloxacin"],
    "ciplox": ["ciprofloxacin"],
    "levoflox": ["levofloxacin"],
    "septran": ["cotrimoxazole"],
    "bactrim": ["cotrimoxazole"],
    "flagyl": ["metronidazole"],
    "metrogyl": ["metronidazole"],
    "shelcal": ["calcium", "vitamin d3"],
    "calcimax": ["calcium", "vitamin d3"],
    "gemcal": ["calcium", "vitamin d3"],
    "uprise": ["vitamin d3"],
    "glycomet": ["metformin"],
    "glucophage": ["metformin"],
    "amaryl": ["glimepiride"],
    "januvia": ["sitagliptin"],
    "telma": ["telmisartan"],
    "amlong": ["amlodipine"],
    "amlopres": ["amlodipine"],
    "losar": ["losartan"],
    "atorva": ["atorvastatin"],
    "lipicure": ["atorvastatin"],
    "rosuvas": ["rosuvastatin"],
    "thyronorm": ["levothyroxine"],
    "eltroxin": ["levothyroxine"],
    "meftal": ["mefenamic acid"],
    "cyclopam": ["dicyclomine", "paracetamol"],
    "drotin": ["drotaverine"],
    "duphaston": ["dydrogesterone"],
    "susten": ["progesterone"],
    "meprate": ["medroxyprogesterone"],
    "fefol": ["iron", "folic acid"],
    "orofer": ["iron"],
    "livogen": ["iron", "folic acid"],
    "folvite": ["folic acid"],
    "myoril": ["thiocolchicoside"],
    "tizan": ["tizanidine"],
    "volini": ["diclofenac topical"],
    "moov": ["topical analgesic"],
    "pregabalin": ["pregabalin"],
    "nurokind": ["methylcobalamin"],
    "neurobion": ["b complex"],
}

# Therapeutic classes for duplicate-class detection.
DRUG_CLASSES: Dict[str, str] = {
    "ibuprofen": "NSAID",
    "diclofenac": "NSAID",
    "aceclofenac": "NSAID",
    "naproxen": "NSAID",
    "etoricoxib": "NSAID",
    "mefenamic acid": "NSAID",
    "aspirin": "NSAID",
    "ketorolac": "NSAID",
    "pantoprazole": "PPI",
    "omeprazole": "PPI",
    "rabeprazole": "PPI",
    "esomeprazole": "PPI",
    "paracetamol": "Antipyretic/analgesic",
    "amoxicillin": "Penicillin antibiotic",
    "ampicillin": "Penicillin antibiotic",
    "cloxacillin": "Penicillin antibiotic",
    "azithromycin": "Macrolide antibiotic",
    "ciprofloxacin": "Fluoroquinolone antibiotic",
    "levofloxacin": "Fluoroquinolone antibiotic",
    "ofloxacin": "Fluoroquinolone antibiotic",
    "atorvastatin": "Statin",
    "rosuvastatin": "Statin",
    "simvastatin": "Statin",
}

# Allergy term -> ingredients that conflict with it.
ALLERGY_CONFLICTS: Dict[str, List[str]] = {
    "penicillin": ["amoxicillin", "ampicillin", "cloxacillin", "clavulanic acid", "penicillin"],
    "amoxicillin": ["amoxicillin", "clavulanic acid"],
    "sulfa": ["cotrimoxazole", "sulfamethoxazole", "sulfasalazine"],
    "sulpha": ["cotrimoxazole", "sulfamethoxazole"],
    "sulphonamide": ["cotrimoxazole", "sulfamethoxazole"],
    "nsaid": [
        "ibuprofen", "diclofenac", "aceclofenac", "naproxen",
        "etoricoxib", "mefenamic acid", "aspirin", "ketorolac",
    ],
    "aspirin": ["aspirin", "ibuprofen", "diclofenac", "naproxen"],
    "ibuprofen": ["ibuprofen"],
    "paracetamol": ["paracetamol"],
    "diclofenac": ["diclofenac"],
    "cephalosporin": ["cefixime", "ceftriaxone", "cefuroxime"],
    "quinolone": ["ciprofloxacin", "levofloxacin", "ofloxacin"],
    "macrolide": ["azithromycin", "erythromycin", "clarithromycin"],
    "metronidazole": ["metronidazole"],
    "iodine": ["povidone iodine", "contrast"],
}

_NOISE = re.compile(
    r"\b(tab|tabs|tablet|cap|caps|capsule|syrup|inj|injection|mg|ml|gm|g|mcg|iu|"
    r"od|bd|tds|qid|sos|hs|daily|twice|thrice|once|per|day|night|morning|"
    r"sr|xr|cr|dt|md|plus|forte)\b",
    re.IGNORECASE,
)
_NUMBERS = re.compile(r"\d+(\.\d+)?")


def normalize_name(raw: str) -> str:
    text = _NUMBERS.sub(" ", raw or "")
    text = _NOISE.sub(" ", text)
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def ingredients_of(raw: str) -> Set[str]:
    """Resolve a free-text medicine name to active ingredients."""
    name = normalize_name(raw)
    if not name:
        return set()
    found: Set[str] = set()
    for brand, ingredients in BRAND_INGREDIENTS.items():
        if re.search(rf"\b{re.escape(brand)}\b", name):
            found.update(ingredients)
    for ingredient in set(DRUG_CLASSES) | {i for v in BRAND_INGREDIENTS.values() for i in v}:
        if re.search(rf"\b{re.escape(ingredient)}\b", name):
            found.add(ingredient)
    return found or {name}


def _label(raw: str) -> str:
    return (raw or "").strip() or "unnamed medicine"


def check_duplicates(medicines: Iterable[str]) -> List[MedicationAlert]:
    """Same ingredient twice, or two drugs of the same risky class."""
    entries = [(m, ingredients_of(m)) for m in medicines if (m or "").strip()]
    alerts: List[MedicationAlert] = []
    seen_pairs: Set[frozenset] = set()

    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            name_a, ing_a = entries[i]
            name_b, ing_b = entries[j]
            pair = frozenset({normalize_name(name_a), normalize_name(name_b)})
            if pair in seen_pairs:
                continue
            if len(pair) < 2:
                # The same medicine written twice. The ingredient comparison
                # below was never reached for it, so the most obvious duplicate
                # there is went unreported.
                seen_pairs.add(pair)
                alerts.append(
                    MedicationAlert(
                        kind="duplicate",
                        severity="serious",
                        medicines_involved=[_label(name_a), _label(name_b)],
                        description=(
                            f"{_label(name_a)} appears twice — the patient may receive a "
                            "double dose of the same drug."
                        ),
                        suggested_action=(
                            "Keep one order, or make the second a clearly different dose or timing."
                        ),
                        detected_by="rule",
                    )
                )
                continue
            shared = ing_a & ing_b
            if shared:
                seen_pairs.add(pair)
                alerts.append(
                    MedicationAlert(
                        kind="duplicate",
                        severity="serious",
                        medicines_involved=[_label(name_a), _label(name_b)],
                        description=(
                            f"Both contain {', '.join(sorted(shared))} — the patient may be "
                            "taking a double dose of the same drug without realising it."
                        ),
                        suggested_action="Confirm what is actually being taken and consolidate to one product.",
                        detected_by="rule",
                    )
                )
                continue
            classes_a = {DRUG_CLASSES[x] for x in ing_a if x in DRUG_CLASSES}
            classes_b = {DRUG_CLASSES[x] for x in ing_b if x in DRUG_CLASSES}
            shared_class = classes_a & classes_b
            if shared_class:
                seen_pairs.add(pair)
                cls = ", ".join(sorted(shared_class))
                alerts.append(
                    MedicationAlert(
                        kind="duplicate",
                        severity="caution",
                        medicines_involved=[_label(name_a), _label(name_b)],
                        description=f"Two {cls} medicines are being taken together.",
                        suggested_action=f"Review whether both {cls} agents are needed.",
                        detected_by="rule",
                    )
                )
    return alerts


def check_allergies(medicines: Iterable[str], allergies: Iterable[str]) -> List[MedicationAlert]:
    """Cross-match the medicine list against recorded allergies, including drug classes."""
    alerts: List[MedicationAlert] = []
    allergy_terms = [a for a in allergies if (a or "").strip()]
    for allergy in allergy_terms:
        allergy_norm = normalize_name(allergy)
        if not allergy_norm:
            continue
        conflicts: Set[str] = set()
        for term, targets in ALLERGY_CONFLICTS.items():
            if term in allergy_norm:
                conflicts.update(targets)
        conflicts.update(w for w in allergy_norm.split() if len(w) > 3)
        for medicine in medicines:
            if not (medicine or "").strip():
                continue
            ingredients = ingredients_of(medicine)
            hit = ingredients & conflicts
            if not hit and any(c in normalize_name(medicine) for c in conflicts if len(c) > 3):
                hit = {normalize_name(medicine)}
            if hit:
                alerts.append(
                    MedicationAlert(
                        kind="allergy",
                        severity="serious",
                        medicines_involved=[_label(medicine)],
                        description=(
                            f"Patient reports an allergy to {allergy.strip()}, and "
                            f"{_label(medicine)} matches it ({', '.join(sorted(hit))})."
                        ),
                        suggested_action="Verify the allergy history before prescribing or continuing this medicine.",
                        detected_by="rule",
                    )
                )
    return alerts


def run_medication_rules(
    medicines: Iterable[str], allergies: Iterable[str]
) -> List[MedicationAlert]:
    medicines = list(medicines)
    return check_allergies(medicines, allergies) + check_duplicates(medicines)
