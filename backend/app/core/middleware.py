"""Cross-cutting HTTP middleware: request identity, rate limiting, security
headers and metrics.

Ordering matters and is asserted in main.py: the request-context middleware
runs outermost so every later layer (including error handlers) can attach the
request id, and the rate limiter runs before anything expensive.
"""
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core import ratelimit
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import metrics

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request and logs the outcome."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(settings.REQUEST_ID_HEADER)
        request_id = incoming or uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            metrics.record_request(request.url.path, 500, duration_ms)
            logger.exception(
                "request_failed",
                extra={"request_id": request_id, "path": request.url.path,
                       "method": request.method, "duration_ms": round(duration_ms, 1)},
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        metrics.record_request(request.url.path, response.status_code, duration_ms)
        response.headers[settings.REQUEST_ID_HEADER] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.1f}"

        if duration_ms > 2000:
            logger.warning(
                "slow_request",
                extra={"request_id": request_id, "path": request.url.path,
                       "duration_ms": round(duration_ms, 1)},
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith(("/api/v1/health", "/metrics", "/docs", "/openapi")):
            return await call_next(request)

        try:
            allowed, budget, remaining, retry_after = await ratelimit.check(request)
        except Exception:  # noqa: BLE001 - a limiter outage must not block care
            logger.exception("rate_limit_check_failed")
            return await call_next(request)

        if not allowed and budget is not None:
            metrics.record_rate_limited(budget.scope)
            logger.warning(
                "rate_limited",
                extra={"path": request.url.path, "scope": budget.scope,
                       "identity": ratelimit.client_identity(request)[:32]},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down and try again shortly.",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(max(retry_after, 1)),
                    "X-RateLimit-Limit": str(budget.requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        if budget is not None:
            response.headers["X-RateLimit-Limit"] = str(budget.requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defence-in-depth headers.

    The API serves JSON and file downloads only, so the CSP can be strict.
    HSTS is emitted only when the request arrived over TLS, so local HTTP
    development is unaffected.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), camera=(), microphone=(self)"
        )
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if forwarded_proto == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
