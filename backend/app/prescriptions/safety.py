"""Deterministic prescribing safety checks.

Runs on every edit of the medicine list, so the doctor sees warnings while
composing rather than after issuing. Everything here is rule-based and
instantaneous — no model call sits between a doctor and a safety warning.

Duplicate and allergy detection reuses `app.ai.pipeline.medication_rules`, the
same engine the copilot uses, so a conflict flagged on the dashboard is flagged
identically at the point of prescribing. Interactions come from the curated
table in `formulary.py`.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from app.ai.pipeline.medication_rules import run_medication_rules
from app.prescriptions.formulary import (
    INTERACTION_PAIRS,
    PREGNANCY_CAUTIONS,
    class_of,
    ingredients_for,
)


@dataclass
class PrescriptionAlert:
    kind: str                    # interaction | duplicate | allergy | pregnancy | formulary
    severity: str                # info | caution | serious
    medicines: List[str] = field(default_factory=list)
    description: str = ""
    suggested_action: Optional[str] = None
    detected_by: str = "rule"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pair_key(a: str, b: str) -> Optional[tuple]:
    if (a, b) in INTERACTION_PAIRS:
        return (a, b)
    if (b, a) in INTERACTION_PAIRS:
        return (b, a)
    return None


def check_interactions(entries: List[Dict[str, Any]]) -> List[PrescriptionAlert]:
    """Cross-check every pair of prescribed medicines against the table."""
    resolved = [
        (entry.get("name") or "", ingredients_for(entry.get("name") or "", entry.get("formulary_code")))
        for entry in entries
    ]
    alerts: List[PrescriptionAlert] = []
    seen: Set[tuple] = set()

    for index_a in range(len(resolved)):
        for index_b in range(index_a + 1, len(resolved)):
            name_a, ingredients_a = resolved[index_a]
            name_b, ingredients_b = resolved[index_b]
            for ingredient_a in ingredients_a:
                for ingredient_b in ingredients_b:
                    key = _pair_key(ingredient_a, ingredient_b)
                    if key is None or key in seen:
                        continue
                    seen.add(key)
                    severity, description, action = INTERACTION_PAIRS[key]
                    alerts.append(
                        PrescriptionAlert(
                            kind="interaction",
                            severity=severity,
                            medicines=[name_a or ingredient_a, name_b or ingredient_b],
                            description=f"{description} ({ingredient_a} + {ingredient_b})",
                            suggested_action=action,
                        )
                    )
    return alerts


def check_pregnancy(
    entries: List[Dict[str, Any]], *, pregnancy_possible: bool
) -> List[PrescriptionAlert]:
    if not pregnancy_possible:
        return []
    alerts: List[PrescriptionAlert] = []
    for entry in entries:
        name = entry.get("name") or ""
        for ingredient in ingredients_for(name, entry.get("formulary_code")):
            caution = PREGNANCY_CAUTIONS.get(ingredient)
            if caution is None:
                continue
            severity, description = caution
            alerts.append(
                PrescriptionAlert(
                    kind="pregnancy",
                    severity=severity,
                    medicines=[name],
                    description=f"{description} ({ingredient})",
                    suggested_action="Confirm pregnancy status before issuing.",
                )
            )
    return alerts


def check_formulary(entries: List[Dict[str, Any]]) -> List[PrescriptionAlert]:
    """Flag rows the doctor should look at before issuing."""
    alerts: List[PrescriptionAlert] = []
    for entry in entries:
        name = (entry.get("name") or "").strip()
        if not name:
            alerts.append(
                PrescriptionAlert(
                    kind="formulary", severity="serious", medicines=[],
                    description="A medicine row has no drug name.",
                    suggested_action="Complete or remove the row.",
                )
            )
            continue
        if not entry.get("formulary_code"):
            alerts.append(
                PrescriptionAlert(
                    kind="formulary", severity="info", medicines=[name],
                    description=f"{name} is not in the hospital formulary.",
                    suggested_action="Confirm the spelling and strength.",
                )
            )
        if not (entry.get("frequency_text") or entry.get("frequency_code")):
            alerts.append(
                PrescriptionAlert(
                    kind="formulary", severity="caution", medicines=[name],
                    description=f"No frequency set for {name}.",
                    suggested_action="Add how often the patient should take it.",
                )
            )
    return alerts


def run_all(
    entries: List[Dict[str, Any]],
    *,
    allergies: Iterable[str] = (),
    pregnancy_possible: bool = False,
) -> List[PrescriptionAlert]:
    """Every deterministic check, ordered with the most serious first."""
    names = [entry.get("name") or "" for entry in entries if (entry.get("name") or "").strip()]

    alerts: List[PrescriptionAlert] = []
    # Duplicates and allergies come from the shared copilot engine.
    for alert in run_medication_rules(names, list(allergies)):
        alerts.append(
            PrescriptionAlert(
                kind=alert.kind,
                severity=alert.severity,
                medicines=alert.medicines_involved,
                description=alert.description,
                suggested_action=alert.suggested_action,
                detected_by=alert.detected_by,
            )
        )
    alerts.extend(check_interactions(entries))
    alerts.extend(check_pregnancy(entries, pregnancy_possible=pregnancy_possible))
    alerts.extend(check_formulary(entries))

    rank = {"serious": 0, "caution": 1, "info": 2}
    alerts.sort(key=lambda alert: rank.get(alert.severity, 3))
    return alerts


def blocking_alerts(alerts: List[PrescriptionAlert]) -> List[PrescriptionAlert]:
    """Alerts a doctor must acknowledge before the prescription can be issued."""
    return [alert for alert in alerts if alert.severity == "serious"]
