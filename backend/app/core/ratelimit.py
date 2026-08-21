"""Fixed-window rate limiting.

Applied as middleware with per-route-class budgets: authentication is the
tightest (credential stuffing), patient intake is next (it is unauthenticated
and creates rows), and normal authenticated traffic is generous.

Identity is the authenticated user when a bearer token is present, otherwise
the client IP taken from the proxy chain. Limits are enforced through the
shared cache, so they are cluster-wide when Redis is configured.
"""
import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

from starlette.requests import Request

from app.core.cache import get_cache
from app.core.config import settings


@dataclass(frozen=True)
class Budget:
    requests: int
    window_s: int
    scope: str


def budget_for(path: str, method: str) -> Optional[Budget]:
    if not settings.RATE_LIMIT_ENABLED:
        return None
    if path.startswith("/api/v1/auth/login"):
        return Budget(settings.RATE_LIMIT_AUTH_PER_MIN, 60, "auth")
    if path.startswith("/api/v1/consultations/start"):
        return Budget(settings.RATE_LIMIT_INTAKE_PER_MIN, 60, "intake")
    if path.startswith("/api/v1/public/"):
        return Budget(settings.RATE_LIMIT_PUBLIC_PER_MIN, 60, "public")
    if "/reports" in path and method == "POST":
        return Budget(settings.RATE_LIMIT_UPLOAD_PER_MIN, 60, "upload")
    if path.startswith("/api/v1/"):
        return Budget(settings.RATE_LIMIT_DEFAULT_PER_MIN, 60, "default")
    return None


def client_identity(request: Request) -> str:
    """Prefer the authenticated subject; fall back to the originating IP."""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        # Hash rather than store the token; we only need a stable bucket key.
        return "u:" + hashlib.sha256(authorization[7:].encode()).hexdigest()[:24]
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return "ip:" + forwarded.split(",")[0].strip()
    return "ip:" + (request.client.host if request.client else "unknown")


async def check(request: Request) -> Tuple[bool, Optional[Budget], int, int]:
    """Returns (allowed, budget, remaining, retry_after_seconds)."""
    budget = budget_for(request.url.path, request.method)
    if budget is None:
        return True, None, 0, 0
    key = f"rl:{budget.scope}:{client_identity(request)}"
    count, remaining_ttl = await get_cache().incr_with_ttl(key, budget.window_s)
    allowed = count <= budget.requests
    remaining = max(budget.requests - count, 0)
    return allowed, budget, remaining, remaining_ttl
