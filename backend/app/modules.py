"""Which parts of the platform this installation runs.

The same codebase serves a hospital with wards, a theatre and a laboratory,
and a clinic that has none of them. Shipping the clinic a build with the ward
board removed would fork the product; leaving the ward board on its sidebar
gives staff a screen that can only ever be empty, and gives an auditor a
module nobody maintains.

So the modules are switched, not deleted, by ENABLED_MODULES in the
environment. A module that is off is off at the router — its endpoints are
never registered and answer 404 — not merely hidden on a screen. Hiding alone
is not a switch: the URL is still there to be typed, and the data is still
there to be written.

Everything a clinic cannot function without — registration, billing,
consultations, prescriptions, ordering investigations, the Visit Pad, the
patient's own uploads — is deliberately not switchable. A switch implies
someone might turn it off, and none of these can be.

The default is every module on, so an existing hospital deployment that sets
nothing keeps the system it has.
"""
from enum import Enum
from typing import Dict, FrozenSet, List, Sequence, Set


class Module(str, Enum):
    """A part of the platform that an installation may not have."""

    LABORATORY = "laboratory"
    IPD = "ipd"
    DIET = "diet"
    THEATRE = "theatre"
    INSURANCE = "insurance"
    ROOM_CHARGES = "room_charges"


# What each module answers for, in the words the hospital would use. Shown in
# the health summary so an operator can see what this node is serving.
MODULE_SUMMARY: Dict[Module, str] = {
    Module.LABORATORY: "In-house laboratory: sample collection, result entry and verification.",
    Module.IPD: "Admissions, wards, beds, nursing charts and discharge.",
    Module.DIET: "Diet orders and the kitchen sheet. Needs admissions.",
    Module.THEATRE: "Operations and procedures, their rooms, consent and notes.",
    Module.INSURANCE: "Insurers, TPAs and employers, and the claims raised against them.",
    Module.ROOM_CHARGES: "The nightly room-charge run for admitted patients. Needs admissions.",
}

# Modules that cannot stand on their own: a diet order belongs to an
# admission, and a room charge is a charge for a bed. Switching the parent off
# switches these off with it rather than leaving a screen that cannot work.
MODULE_REQUIRES: Dict[Module, Module] = {
    Module.DIET: Module.IPD,
    Module.ROOM_CHARGES: Module.IPD,
}


class UnknownModuleError(ValueError):
    """ENABLED_MODULES named something that is not a module."""


def parse_enabled(raw: str) -> FrozenSet[Module]:
    """Read the ENABLED_MODULES setting.

    "all" (the default) is every module. Otherwise a comma-separated list of
    module names; an empty list means a clinic running only the core. A name
    that is not a module is a typo in the environment, and a typo that
    silently disabled a ward would be discovered by a nurse, so it raises.
    """
    value = (raw or "").strip()
    if value.lower() == "all":
        return frozenset(Module)

    names = [part.strip().lower() for part in value.split(",") if part.strip()]
    known = {m.value: m for m in Module}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise UnknownModuleError(
            "ENABLED_MODULES names unknown module(s): " + ", ".join(sorted(unknown))
            + ". Known modules: " + ", ".join(sorted(known)) + "."
        )
    return frozenset(known[n] for n in names)


def resolve(enabled: Sequence[Module] | Set[Module] | FrozenSet[Module]) -> FrozenSet[Module]:
    """Drop modules whose parent module is off.

    Done here rather than trusted to whoever wrote the .env: "diet without
    admissions" is not a configuration anyone means, and a kitchen sheet for
    patients who cannot exist is worse than no kitchen sheet.
    """
    result = set(enabled)
    changed = True
    while changed:  # a chain of requirements settles in one or two passes
        changed = False
        for module, parent in MODULE_REQUIRES.items():
            if module in result and parent not in result:
                result.discard(module)
                changed = True
    return frozenset(result)


def dropped_for_missing_parent(
    requested: FrozenSet[Module], resolved: FrozenSet[Module]
) -> List[str]:
    """Human-readable note of what resolve() turned off, for the startup log."""
    return sorted(
        f"{module.value} (needs {MODULE_REQUIRES[module].value})"
        for module in requested - resolved
        if module in MODULE_REQUIRES
    )
