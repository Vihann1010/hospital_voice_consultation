#!/usr/bin/env python3
"""Bring a brand-new, empty database up to the current schema.

    python -m scripts.migrate_fresh_install

`0001_initial` builds today's entire schema in one step; everything after it
exists to carry an *already-running* deployment forward incrementally, and
replaying that history on an empty database makes several of them try to
create a table `0001` just built — "relation already exists". See
docs/DEPLOYMENT.md section 4 for the full explanation.

This runs `alembic upgrade 0001_initial` for real, then `alembic stamp head`
to mark the rest as already applied without executing their DDL. Refuses to
run against a database that already has tables in it — that is an existing
deployment, which docs/DEPLOYMENT.md's other two paths cover instead.
"""
import subprocess
import sys

sys.path.insert(0, ".")

from sqlalchemy import create_engine, inspect  # noqa: E402

from app.core.config import settings  # noqa: E402


def _sync_database_url() -> str:
    # The app's async URL (asyncpg) isn't a driver `sqlalchemy.inspect` can
    # use synchronously; swap in psycopg2, which is already a dependency
    # (alembic itself uses it) for this one inspection query.
    return (
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def main() -> None:
    engine = create_engine(_sync_database_url())
    existing = inspect(engine).get_table_names()
    engine.dispose()

    if existing:
        print(
            f"Refusing to run: {settings.POSTGRES_DB} already has "
            f"{len(existing)} table(s) (e.g. {existing[0]}). This script is "
            "for a genuinely empty database only — see docs/DEPLOYMENT.md "
            "section 4 for the other two migration paths."
        )
        sys.exit(1)

    print(f"{settings.POSTGRES_DB} is empty — building the schema.")
    subprocess.run(["alembic", "upgrade", "0001_initial"], check=True)
    subprocess.run(["alembic", "stamp", "head"], check=True)
    print("Done. The database is at head; migrations 0002 onward were "
          "marked applied without re-running their DDL, which 0001 already "
          "covers on a fresh install.")


if __name__ == "__main__":
    main()
