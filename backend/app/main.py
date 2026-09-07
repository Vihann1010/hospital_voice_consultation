"""Satya Hospital AI Platform — API entrypoint.

Startup order matters and is deliberate:
  1. validate configuration (refuse to boot production with shipped defaults)
  2. verify the schema is migrated — the app no longer creates tables itself
  3. seed accounts, warm the cache backend, start background workers
  4. only then mark the node ready, so the load balancer sends no traffic to a
     half-initialised process

Shutdown reverses it, draining in-flight work before closing pools.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.llm_client import llm_client
from app.ai.providers.factory import close_gateway
from app.ai.session.manager import session_manager
from app.api.v1.router import api_router
from app.api.v1.routes.health import mark_ready
from app.core.cache import close_cache, get_cache
from app.core.config import assert_production_ready, settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.session import AsyncSessionLocal, engine
from app.messaging.factory import close_provider, get_provider
from app.services.auth_service import seed_default_users
from app.services.delivery_service import retry_worker

configure_logging()
logger = get_logger(__name__)

REQUIRED_TABLES = ("users", "patients", "consultations", "prescriptions", "audit_logs")


async def _verify_schema() -> None:
    """Fail fast if migrations have not been applied.

    The platform used to call `create_all` on boot. That silently diverges from
    the models the moment a column changes, so schema management now belongs to
    Alembic alone and the app only checks the work was done.
    """
    async with engine.begin() as connection:
        result = await connection.execute(
            text("SELECT table_name FROM information_schema.tables "
                 "WHERE table_schema = 'public'")
        )
        present = {row[0] for row in result}
    missing = [table for table in REQUIRED_TABLES if table not in present]
    if missing:
        raise RuntimeError(
            "The database schema is not up to date. Missing tables: "
            + ", ".join(missing) + ".\nRun:  alembic upgrade head"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_production_ready(settings)
    await _verify_schema()

    async with AsyncSessionLocal() as session:
        await seed_default_users(session)

    cache = get_cache()
    if not await cache.ping():
        logger.warning("cache_unavailable_at_startup", extra={"backend": cache.name})
    get_provider()      # surface messaging misconfiguration at boot, not first send
    retry_worker.start()

    mark_ready(True)
    logger.info("startup_complete",
                extra={"env": settings.APP_ENV, "cache": cache.name,
                       "llm_provider": settings.LLM_PROVIDER})

    yield

    # --- graceful shutdown -------------------------------------------------
    mark_ready(False)   # stop taking new traffic before tearing anything down
    logger.info("shutdown_started")
    await asyncio.sleep(min(settings.SHUTDOWN_GRACE_S * 0.1, 2.0))

    await retry_worker.stop()
    await session_manager.shutdown()
    await close_provider()
    await close_gateway()
    await llm_client.aclose()
    await close_cache()
    await engine.dispose()
    logger.info("shutdown_complete")


app = FastAPI(
    title=settings.APP_NAME,
    version="5.0.0",
    description=(
        "Backend for Satya Hospital's AI voice intake platform.\n\n"
        "Departments: Orthopedics (Dr. A K Agarwal) and Gynecology "
        "(Dr. Manisha Agarwal).\n\n"
        "All clinical endpoints require a bearer token from `/auth/login`. "
        "AI output is advisory throughout; the treating doctor is the final "
        "authority on every clinical decision."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" or settings.DEBUG else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" or settings.DEBUG else None,
    openapi_url="/openapi.json",
    swagger_ui_parameters={"persistAuthorization": True},
)

# Middleware runs in reverse registration order, so the last registered runs
# first. Request context must be outermost to tag everything below it.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization", "Content-Type", "X-Finance-Unlock", settings.REQUEST_ID_HEADER,
    ],
    expose_headers=[settings.REQUEST_ID_HEADER, "X-RateLimit-Remaining", "Retry-After"],
    max_age=600,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail,
                 "request_id": getattr(request.state, "request_id", None)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Some of the submitted values were not valid.",
            "errors": [
                {"field": ".".join(str(part) for part in error.get("loc", [])[1:]),
                 "message": error.get("msg")}
                for error in exc.errors()[:10]
            ],
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Never leak a stack trace to a client; always leave a traceable id."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled_exception",
                     extra={"request_id": request_id, "path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong on our side. The technical team "
                           "has been notified.",
                 "request_id": request_id},
    )


app.include_router(api_router, prefix=settings.API_V1_PREFIX)
