#!/usr/bin/env bash
# Apply migrations, then hand off to the API. Used when a separate migration
# service is not practical (single-host deployments).
set -euo pipefail

echo "[entrypoint] waiting for the database…"
for attempt in $(seq 1 30); do
    if python -c "
import asyncio, sys
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
async def check():
    engine = create_async_engine(settings.database_url)
    async with engine.connect():
        pass
    await engine.dispose()
asyncio.run(check())
" 2>/dev/null; then
        echo "[entrypoint] database is up"
        break
    fi
    [ "${attempt}" -eq 30 ] && { echo "[entrypoint] database never became ready"; exit 1; }
    sleep 2
done

echo "[entrypoint] applying migrations…"
alembic upgrade head

echo "[entrypoint] starting API…"
exec "$@"
