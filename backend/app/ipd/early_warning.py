"""NEWS2 — National Early Warning Score 2.

A ward patient who is deteriorating usually shows it in the observations
hours before anyone notices. NEWS2 is the Royal College of Physicians'
standard for turning a set of vitals into an escalation decision, and it is
used across the NHS and widely in Indian private hospitals.

It is implemented here as arithmetic, deliberately, and this is the most
important design decision in the module: **a deteriorating patient must never
depend on a language model being available, in budget, or correct.** The score
is a lookup table. It runs with the network down. A model may later summarise
the trend in prose, but it does not decide whether to call a doctor.

Scoring (RCP, 2017 revision):

  parameter                    3      2      1      0      1      2      3
  respiration /min            ≤8            9-11  12-20        21-24   ≥25
  SpO2 scale 1 %              ≤91   92-93  94-95   ≥96
  air or oxygen                      oxygen        air
  systolic BP mmHg            ≤90   91-100 101-110 111-219             ≥220
  pulse /min                  ≤40           41-50  51-90  91-110 111-130 ≥131
  consciousness (ACVPU)                            alert          not alert(3)
  temperature °C              ≤35.0        35.1-36.0 36.1-38.0 38.1-39.0 ≥39.1

Escalation:
  0            routine monitoring, 12-hourly
  1-4          nurse assessment, 4-6 hourly
  3 in any one parameter   urgent nurse review, hourly
  5-6          urgent doctor review, 1-hourly
  ≥7           emergency, continuous monitoring, critical care input

SpO2 Scale 2 (for patients with hypercapnic respiratory failure, e.g. COPD
with a target of 88-92%) is supported because scoring a COPD patient on
Scale 1 flags them as deteriorating when they are at their own baseline —
a false alarm that trains staff to ignore the score.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class VitalsError(ValueError):
    pass


@dataclass
class Vitals:
    """One set of bedside observations. Any field may be missing."""

    respiratory_rate: Optional[int] = None          # breaths per minute
    spo2_percent: Optional[int] = None
    on_oxygen: bool = False
    systolic_bp: Optional[int] = None               # mmHg
    pulse: Optional[int] = None                     # beats per minute
    temperature_c: Optional[float] = None
    consciousness: Optional[str] = None             # A C V P U
    # Scale 2 applies only where a clinician has prescribed a lower target.
    spo2_scale_2: bool = False


@dataclass
class ParameterScore:
    parameter: str
    value: str
    score: int


@dataclass
class NewsResult:
    total: int
    parameters: List[ParameterScore] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    highest_single: int = 0
    risk: str = "low"
    response: str = ""
    monitoring: str = ""
    # True when a parameter scores 3 on its own, which escalates regardless
    # of the total — a patient can be gravely unwell on one axis alone.
    red_score: bool = False

    @property
    def is_complete(self) -> bool:
        return not self.missing


def _score_respiration(rate: int) -> int:
    if rate <= 8:
        return 3
    if rate <= 11:
        return 1
    if rate <= 20:
        return 0
    if rate <= 24:
        return 2
    return 3


def _score_spo2_scale_1(value: int) -> int:
    if value <= 91:
        return 3
    if value <= 93:
        return 2
    if value <= 95:
        return 1
    return 0


def _score_spo2_scale_2(value: int, on_oxygen: bool) -> int:
    """Scale 2: the target range is 88-92%, and being ABOVE it on oxygen
    scores, because over-oxygenation is the danger in this group."""
    if value <= 83:
        return 3
    if value <= 85:
        return 2
    if value <= 87:
        return 1
    if value <= 92:
        return 0
    if not on_oxygen:
        return 0
    if value <= 94:
        return 1
    if value <= 96:
        return 2
    return 3


def _score_systolic(value: int) -> int:
    if value <= 90:
        return 3
    if value <= 100:
        return 2
    if value <= 110:
        return 1
    if value <= 219:
        return 0
    return 3


def _score_pulse(value: int) -> int:
    if value <= 40:
        return 3
    if value <= 50:
        return 1
    if value <= 90:
        return 0
    if value <= 110:
        return 1
    if value <= 130:
        return 2
    return 3


def _score_temperature(value: float) -> int:
    if value <= 35.0:
        return 3
    if value <= 36.0:
        return 1
    if value <= 38.0:
        return 0
    if value <= 39.0:
        return 1
    return 2


def _score_consciousness(level: str) -> int:
    """ACVPU: Alert, new Confusion, Voice, Pain, Unresponsive.

    Anything other than Alert scores 3. New confusion is included in NEWS2
    precisely because it is missed so often.
    """
    return 0 if (level or "").strip().upper().startswith("A") else 3


def score_news2(vitals: Vitals) -> NewsResult:
    """Score one set of observations.

    Missing parameters are reported rather than assumed normal. A score of 2
    computed from three of seven parameters is not reassurance, and the ward
    interface says so.
    """
    result = NewsResult(total=0)

    def record(name: str, value, score: int) -> None:
        result.parameters.append(ParameterScore(name, str(value), score))
        result.total += score
        result.highest_single = max(result.highest_single, score)

    if vitals.respiratory_rate is None:
        result.missing.append("respiratory rate")
    else:
        if not 0 < vitals.respiratory_rate < 100:
            raise VitalsError("Respiratory rate is outside a plausible range.")
        record("Respiration", f"{vitals.respiratory_rate}/min",
               _score_respiration(vitals.respiratory_rate))

    if vitals.spo2_percent is None:
        result.missing.append("oxygen saturation")
    else:
        if not 50 <= vitals.spo2_percent <= 100:
            raise VitalsError("SpO2 is outside a plausible range.")
        score = (
            _score_spo2_scale_2(vitals.spo2_percent, vitals.on_oxygen)
            if vitals.spo2_scale_2
            else _score_spo2_scale_1(vitals.spo2_percent)
        )
        scale = "scale 2" if vitals.spo2_scale_2 else "scale 1"
        record(f"SpO2 ({scale})", f"{vitals.spo2_percent}%", score)

    # Supplemental oxygen is itself worth 2 points.
    record("Air or oxygen", "oxygen" if vitals.on_oxygen else "air",
           2 if vitals.on_oxygen else 0)

    if vitals.systolic_bp is None:
        result.missing.append("blood pressure")
    else:
        if not 40 <= vitals.systolic_bp <= 300:
            raise VitalsError("Systolic blood pressure is outside a plausible range.")
        record("Systolic BP", f"{vitals.systolic_bp} mmHg",
               _score_systolic(vitals.systolic_bp))

    if vitals.pulse is None:
        result.missing.append("pulse")
    else:
        if not 20 <= vitals.pulse <= 250:
            raise VitalsError("Pulse is outside a plausible range.")
        record("Pulse", f"{vitals.pulse}/min", _score_pulse(vitals.pulse))

    if vitals.consciousness is None:
        result.missing.append("consciousness")
    else:
        record("Consciousness", vitals.consciousness.upper()[:1],
               _score_consciousness(vitals.consciousness))

    if vitals.temperature_c is None:
        result.missing.append("temperature")
    else:
        if not 25.0 <= vitals.temperature_c <= 45.0:
            raise VitalsError("Temperature is outside a plausible range.")
        record("Temperature", f"{vitals.temperature_c:.1f} °C",
               _score_temperature(vitals.temperature_c))

    result.red_score = result.highest_single >= 3
    result.risk, result.response, result.monitoring = _escalation(
        result.total, result.red_score
    )
    return result


def _escalation(total: int, red_score: bool) -> tuple:
    """The RCP escalation table. A single 3 escalates on its own."""
    if total >= 7:
        return (
            "critical",
            "Emergency response. Call the duty doctor immediately and involve "
            "critical care.",
            "Continuous monitoring",
        )
    if total >= 5:
        return (
            "high",
            "Urgent review by the duty doctor. Escalate to critical care if "
            "the patient does not improve.",
            "Hourly observations",
        )
    if red_score:
        return (
            "medium",
            "One parameter is severely abnormal. Urgent review by the nurse "
            "in charge and inform the treating doctor.",
            "Hourly observations",
        )
    if total >= 1:
        return (
            "low",
            "Assessment by a registered nurse, who decides whether the "
            "frequency of monitoring should increase.",
            "4 to 6 hourly observations",
        )
    return ("none", "Continue routine monitoring.", "12 hourly observations")


def trend(results: List[NewsResult]) -> Dict[str, object]:
    """Direction of travel across successive observations.

    A patient at 4 and rising is more concerning than one at 4 and falling,
    and the single most useful thing to show at a handover.
    """
    scores = [item.total for item in results if item.is_complete or item.total]
    if len(scores) < 2:
        return {"direction": "insufficient", "change": 0, "scores": scores}
    change = scores[-1] - scores[0]
    if change >= 2:
        direction = "deteriorating"
    elif change <= -2:
        direction = "improving"
    else:
        direction = "stable"
    return {"direction": direction, "change": change, "scores": scores}
