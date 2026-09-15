"""Keeping the books up to date with the counter, every few minutes.

A run posts what is new or changed since the last successful run (with a few
minutes' overlap, which costs nothing because unchanged records are skipped).
A full run re-checks every record, and is what to use after a bug fix or a
migration. Like the room-charge run: an advisory lock makes a second
concurrent run skip, and every run is a row in `job_runs`.
"""
import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text

from app.core.clock import local_today
from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal

logger = get_logger(__name__)

JOB = "books_posting"
LOCK_KEY = 72_417_002
OVERLAP = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def run_books_posting(*, triggered_by: str, full: bool = False):
    from app.models.job_run import JobRun
    from app.services.accounts_service import AccountsService

    async with AsyncSessionLocal() as ledger:
        since = None
        if not full:
            last = (await ledger.execute(
                select(JobRun).where(JobRun.job == JOB, JobRun.status.in_(["done", "partial"]))
                .order_by(JobRun.started_at.desc()).limit(1)
            )).scalar_one_or_none()
            since = (last.started_at - OVERLAP) if last is not None else None
        run = JobRun(job=JOB, run_on=local_today(), started_at=_now(), status="running",
                     triggered_by=triggered_by, summary={})
        ledger.add(run)
        await ledger.commit()
        run_id = run.id

    status, summary, error = "failed", {}, None
    try:
        async with AsyncSessionLocal() as work:
            async with work.begin():
                locked = (await work.execute(text("SELECT pg_try_advisory_xact_lock(:key)"),
                                             {"key": LOCK_KEY})).scalar()
                if not locked:
                    status, error = "skipped", "Another posting run was already in progress."
                else:
                    summary = await AccountsService(work).run_posting(since=since)
                    status = "partial" if summary["failed"] else "done"
    except Exception as exc:  # noqa: BLE001
        logger.exception("books_posting_failed")
        status, error = "failed", f"The run stopped: {str(exc)[:300]}"

    async with AsyncSessionLocal() as ledger:
        run = await ledger.get(JobRun, run_id)
        run.status, run.summary, run.error, run.finished_at = status, summary, error, _now()
        await ledger.commit()
        await ledger.refresh(run)
    logger.info("books_posting_run", extra={"status": status,
                                            **{k: v for k, v in summary.items() if k != "exceptions"}})
    return run


class BooksPostingWorker:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if not settings.BOOKS_POSTING_ENABLED:
            logger.info("books_posting_worker_disabled")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.BOOKS_POSTING_INTERVAL_S)
                await run_books_posting(triggered_by="schedule")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the worker must survive a bad run
                logger.exception("books_posting_worker_error")


books_posting_worker = BooksPostingWorker()
