"""Shared fixtures.

Integration tests share one engine and wrap each test in a transaction that is
rolled back, which is far faster than recreating the schema per test and keeps
tests isolated from one another.
"""
import asyncio
import os
from typing import AsyncIterator

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("MESSAGING_PROVIDER", "console")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _database_available() -> bool:
    import socket

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


requires_db = pytest.mark.skipif(
    not _database_available(),
    reason="PostgreSQL is not reachable; start it with `docker compose up -d db`",
)


@pytest.fixture(scope="session")
async def engine():
    from app.db.session import engine as app_engine
    from app.models.registry import Base

    async with app_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield app_engine
    await app_engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator:
    """A session bound to a transaction that is always rolled back."""
    from sqlalchemy.ext.asyncio import AsyncSession

    async with engine.connect() as connection:
        transaction = await connection.begin()
        async_session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield async_session
        finally:
            await async_session.close()
            await transaction.rollback()


@pytest.fixture
async def client():
    """HTTP client bound to the app without starting a server."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
