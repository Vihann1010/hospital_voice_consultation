"""The practices a site houses, each its own business.

One building can hold two practices that share a front desk and nothing
else: CN Gastrocare and Smile Dental each register their own patients, number
their own bills, and keep their own records. A patient of both is two
patients, one in each, exactly as they would be across the road.

A practice is three letters, a name and the departments it runs:

    PRACTICES=CNG=CN Gastrocare:gastroenterology;SMD=Smile Dental:dentistry

The three letters begin the practice's UHIDs (CNG26…, SMD26…), its bill
numbers (CNG/26-27/…) and its prescription numbers. They are permanent once a
patient is registered.

A site that sets nothing is one practice: DOCUMENT_PREFIX, HOSPITAL_NAME and
every department, which is what every existing deployment is.

The first practice listed is the site's default. Its numbering continues the
counters the site had before practices existed, so turning this on does not
restart anybody's series.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.models.enums import Department


@dataclass(frozen=True)
class Practice:
    prefix: str
    name: str
    departments: Tuple[Department, ...]

    def scope(self, kind: str, *, default: bool) -> str:
        """The counter a number is drawn from: the old one for the default."""
        return kind if default else f"{kind}:{self.prefix}"


class PracticeConfigError(ValueError):
    """PRACTICES does not describe a coherent set of practices."""


def parse(raw: str) -> List[Practice]:
    practices: List[Practice] = []
    for chunk in (raw or "").split(";"):
        if not chunk.strip():
            continue
        prefix, sep, rest = chunk.partition("=")
        name, sep2, departments = rest.rpartition(":")
        prefix = prefix.strip().upper()
        if not sep or not sep2 or not name.strip():
            raise PracticeConfigError(
                f"'{chunk.strip()}' is not PREFIX=Name:department,department "
                "(e.g. SMD=Smile Dental:dentistry)."
            )
        if len(prefix) != 3 or not prefix.isalpha():
            raise PracticeConfigError(f"'{prefix}' must be exactly three letters.")
        try:
            owned = tuple(Department(d.strip().lower()) for d in departments.split(",") if d.strip())
        except ValueError as exc:
            raise PracticeConfigError(f"{exc} in '{chunk.strip()}'.") from None
        if not owned:
            raise PracticeConfigError(f"Practice {prefix} names no department.")
        practices.append(Practice(prefix=prefix, name=name.strip(), departments=owned))

    prefixes = [p.prefix for p in practices]
    if len(set(prefixes)) != len(prefixes):
        raise PracticeConfigError("Two practices share the same three letters.")
    seen: Dict[Department, str] = {}
    for practice in practices:
        for department in practice.departments:
            if department in seen:
                raise PracticeConfigError(
                    f"{department.value} is in both {seen[department]} and {practice.prefix}; "
                    "a department belongs to one practice."
                )
            seen[department] = practice.prefix
    return practices


def _settings():
    from app.core.config import settings
    return settings


def all_practices() -> List[Practice]:
    settings = _settings()
    configured = parse(settings.PRACTICES)
    if configured:
        return configured
    return [Practice(prefix=settings.DOCUMENT_PREFIX, name=settings.HOSPITAL_NAME,
                     departments=tuple(Department))]


def default_practice() -> Practice:
    return all_practices()[0]


def by_prefix(prefix: Optional[str]) -> Practice:
    """The practice with these letters, or the default for a legacy record."""
    for practice in all_practices():
        if practice.prefix == (prefix or "").upper():
            return practice
    return default_practice()


def for_department(department: Optional[Department]) -> Practice:
    if department is not None:
        for practice in all_practices():
            if department in practice.departments:
                return practice
    return default_practice()


def is_default(practice: Practice) -> bool:
    return practice.prefix == default_practice().prefix


def counter_scope(kind: str, practice: Practice) -> str:
    return practice.scope(kind, default=is_default(practice))


def prefixes() -> List[str]:
    return [p.prefix for p in all_practices()]
