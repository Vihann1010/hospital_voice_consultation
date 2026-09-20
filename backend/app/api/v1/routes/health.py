"""Health, readiness and metrics endpoints.

Three distinct probes, because Kubernetes and Docker ask three different
questions:

  /health/live    Is the process alive? Never touches a dependency, so a slow
                  database can never cause a restart loop.
  /health/ready   Can it serve traffic? Checks the database and cache. A false
                  answer removes this replica from the load balancer.
  /health         Human-readable summary of everything, for operators.
"""
import time
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.cache import response_cache
from app.ai.providers.cost import cost_tracker
from app.ai.session.manager import session_manager
from app.api.deps import DbSession, require_permission
from app.core.permissions import Permission
from app.core.cache import get_cache
from app.core.config import settings
from app.core.metrics import metrics
from app.investigations.extraction import extraction_capabilities
from app.messaging.factory import get_provider
from app.models.enums import UserRole
from app.modules import Module
from app.prescriptions.formulary import unapproved_departments
from app.prescriptions.pdf import pdf_capabilities

router = APIRouter(tags=["health"])

_STARTED_AT = time.time()
_READY = {"value": False}


def mark_ready(ready: bool = True) -> None:
    """Flipped by the lifespan handler once startup work has finished."""
    _READY["value"] = ready


@router.get("/health/live")
async def liveness() -> Dict[str, Any]:
    """Liveness: no dependencies, so a database blip never restarts the pod."""
    return {"status": "alive", "uptime_seconds": round(time.time() - _STARTED_AT, 1)}


@router.get("/health/ready")
async def readiness(session: DbSession, response: Response) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    healthy = True

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"ok": False, "error": repr(exc)[:200]}
        healthy = False

    cache = get_cache()
    try:
        cache_ok = await cache.ping()
        checks["cache"] = {
            "ok": cache_ok, "backend": cache.name, "distributed": cache.distributed,
        }
        if not cache_ok:
            healthy = False
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = {"ok": False, "error": repr(exc)[:200]}
        healthy = False

    checks["accepting_traffic"] = {"ok": _READY["value"]}
    if not _READY["value"]:
        healthy = False

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if healthy else "not_ready", "checks": checks}


@router.get("/health")
async def health(session: DbSession, response: Response) -> Dict[str, Any]:
    """Operator-facing summary: dependencies plus what this node can do."""
    database_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database_ok = False

    cache = get_cache()
    try:
        cache_ok = await cache.ping()
    except Exception:  # noqa: BLE001
        cache_ok = False

    if not (database_ok and cache_ok):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if database_ok and cache_ok else "degraded",
        "environment": settings.APP_ENV,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "dependencies": {
            "database": database_ok,
            "cache": {"ok": cache_ok, "backend": cache.name,
                      "distributed": cache.distributed},
        },
        "formulary_pending_signoff": [d.value for d in unapproved_departments()],
        "modules": {
            "enabled": sorted(m.value for m in settings.enabled_modules),
            "disabled": sorted(
                m.value for m in Module if m not in settings.enabled_modules
            ),
        },
        "capabilities": {
            **pdf_capabilities(),
            **extraction_capabilities(),
            "messaging_provider": get_provider().name,
            "llm_provider": settings.LLM_PROVIDER,
        },
        "runtime": {
            **metrics.snapshot(),
            "voice_sessions": session_manager.stats(),
            "ai_response_cache": response_cache.stats(),
            "llm_usage": cost_tracker.snapshot(),
        },
    }


@router.get("/config")
async def client_config() -> Dict[str, Any]:
    """What the front end needs before anyone signs in.

    Chiefly the module list: the sidebar and the Settings hub must not offer a
    ward board to a clinic that has no ward. Read from the same setting the
    router registers from, so a screen cannot be shown for an endpoint that
    does not exist.

    Deliberately unauthenticated and deliberately dull — the hospital's name,
    which is printed on every prescription, and which optional modules are
    switched on. Nothing here is a secret, and requiring a token would mean the
    login screen could not render the hospital it belongs to.
    """
    return {
        "hospital_name": settings.HOSPITAL_NAME,
        "hospital_city": settings.HOSPITAL_CITY,
        "modules": sorted(m.value for m in settings.enabled_modules),
        # Departments whose drafted prescribing content is still withheld. A
        # doctor searching a near-empty formulary deserves to be told why
        # rather than concluding the system is broken.
        "formulary_pending_signoff": [d.value for d in unapproved_departments()],
    }


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Prometheus scrape target."""
    if not settings.METRICS_ENABLED:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return Response(content=metrics.prometheus(), media_type="text/plain; version=0.0.4")


@router.get(
    "/health/permissions",
    dependencies=[Depends(require_permission(Permission.SYSTEM_ADMIN))],
    include_in_schema=False,
)
async def permission_matrix() -> Dict[str, Any]:
    """The live RBAC matrix, for auditors and the deployment checklist."""
    from app.core.permissions import matrix

    return {"matrix": matrix()}
