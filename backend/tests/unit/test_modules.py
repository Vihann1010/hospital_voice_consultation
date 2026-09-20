"""The module switch.

What matters here is that "off" means off: not registered, not scheduled, not
merely hidden. And that a typo in the environment is loud, because the quiet
version of that bug is a ward that stopped working overnight.
"""
import pytest

from app.modules import (
    MODULE_REQUIRES,
    MODULE_SUMMARY,
    Module,
    UnknownModuleError,
    dropped_for_missing_parent,
    parse_enabled,
    resolve,
)

pytestmark = pytest.mark.unit


def test_default_is_every_module():
    """An existing hospital that sets nothing keeps the system it has."""
    assert parse_enabled("all") == frozenset(Module)


def test_names_are_read_case_and_space_insensitively():
    assert parse_enabled(" Laboratory , IPD ") == {Module.LABORATORY, Module.IPD}


def test_empty_means_core_only():
    assert parse_enabled("") == frozenset()
    assert parse_enabled("   ") == frozenset()


def test_unknown_module_raises():
    """A typo must not silently disable a ward."""
    with pytest.raises(UnknownModuleError) as exc:
        parse_enabled("laboratory,warda")
    assert "warda" in str(exc.value)


def test_dependent_module_is_dropped_without_its_parent():
    """A kitchen sheet for patients who cannot be admitted is worse than none."""
    resolved = resolve({Module.DIET, Module.ROOM_CHARGES, Module.THEATRE})
    assert resolved == {Module.THEATRE}


def test_dependent_module_survives_with_its_parent():
    resolved = resolve({Module.IPD, Module.DIET, Module.ROOM_CHARGES})
    assert resolved == {Module.IPD, Module.DIET, Module.ROOM_CHARGES}


def test_dropping_is_reported_for_the_startup_log():
    requested = parse_enabled("diet,theatre")
    notes = dropped_for_missing_parent(requested, resolve(requested))
    assert notes == ["diet (needs ipd)"]


def test_every_module_is_described_and_every_requirement_is_real():
    for module in Module:
        assert MODULE_SUMMARY.get(module), f"{module.value} has no summary"
    for module, parent in MODULE_REQUIRES.items():
        assert isinstance(parent, Module)
        assert parent not in MODULE_REQUIRES, "requirement chains are not expected"


def test_gastro_clinic_profile():
    """The clinic this branch is for: procedures, no beds, no bench, no TPA."""
    resolved = resolve(parse_enabled("theatre"))
    assert resolved == {Module.THEATRE}
    for absent in (Module.LABORATORY, Module.IPD, Module.DIET,
                   Module.INSURANCE, Module.ROOM_CHARGES):
        assert absent not in resolved


# --------------------------------------------------------------- the router


def _registered_prefixes(enabled: str) -> set:
    """Rebuild the API router with a given ENABLED_MODULES and list its paths."""
    import importlib

    from app.core.config import settings

    original = settings.ENABLED_MODULES
    settings.ENABLED_MODULES = enabled
    try:
        import app.api.v1.router as router_module

        importlib.reload(router_module)
        return {
            route.path
            for route in router_module.api_router.routes
            if getattr(route, "path", None)
        }
    finally:
        settings.ENABLED_MODULES = original
        import app.api.v1.router as router_module

        importlib.reload(router_module)


def _has_prefix(paths: set, prefix: str) -> bool:
    return any(path.startswith(prefix) for path in paths)


def test_disabled_modules_are_not_registered_at_all():
    """Off means the endpoint does not exist, not that a link was hidden."""
    paths = _registered_prefixes("theatre")
    assert _has_prefix(paths, "/theatre")
    for absent in ("/lab", "/ipd", "/diet", "/insurance"):
        assert not _has_prefix(paths, absent), f"{absent} should not be served"


def test_core_endpoints_are_never_switchable():
    """A clinic with no modules at all still registers, bills and consults."""
    paths = _registered_prefixes("")
    for core in ("/patients", "/reception", "/consultations", "/prescriptions",
                 "/investigations", "/finance", "/pads", "/auth"):
        assert _has_prefix(paths, core), f"{core} must always be served"


def test_all_modules_are_registered_by_default():
    paths = _registered_prefixes("all")
    for served in ("/lab", "/ipd", "/diet", "/insurance", "/theatre"):
        assert _has_prefix(paths, served)


# ------------------------------------------------ the installation's default


def test_default_department_is_configured_not_hardcoded():
    """Three handlers used to file a departmentless clinician under orthopedics."""
    from app.core.config import Settings
    from app.models.enums import Department

    assert Settings(DEFAULT_DEPARTMENT="gastroenterology").default_department is (
        Department.GASTROENTEROLOGY
    )
    assert Settings(DEFAULT_DEPARTMENT=" Gynecology ").default_department is (
        Department.GYNECOLOGY
    )


def test_default_department_must_be_a_real_department():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(DEFAULT_DEPARTMENT="pediatrics")
