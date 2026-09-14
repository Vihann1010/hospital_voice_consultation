"""Posting room charges every morning, for every admitted patient.

The rule for which bed-day is owed is in `app/ipd/bed_days.py`: a day is
charged for the bed held at the census hour. So the run happens after that
hour, not at midnight — at midnight today's bed is not yet decided.

Three properties make it safe to leave running:

* **Idempotent.** Accrual skips days already posted, so a run that fires
  twice, or a manual run after the scheduled one, charges nobody twice.
* **One at a time.** The work holds a transaction-level advisory lock; a
  second run that starts while one is going is recorded as skipped.
* **Accounted for.** Every run is a row in `job_runs` with how many
  admissions were visited, how many charges were posted, and which
  admissions failed and why. One failing admission does not stop the rest.
"""
import asyncio
import contextlib
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text

from app.core.clock import local_now, local_today
from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal

logger = get_logger(__name__)

JOB = "room_charges"
LOCK_KEY = 72_417_001  # an arbitrary constant naming this job's advisory lock
AUTOMATIC = "Room charges (automatic)"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_time() -> time:
    try:
        hour, minute = (int(part) for part in settings.BED_CHARGE_RUN_AT.split(":"))
        return time(hour=hour, minute=minute)
    except (ValueError, AttributeError):
        return time(hour=8, minute=30)


async def run_room_charges(*, triggered_by: str):
    """Post charges for every current admission. Returns the JobRun."""
    from app.models.enums import AdmissionStatus
    from app.models.ipd import Admission
    from app.models.job_run import JobRun
    from app.services.ipd_service import IPDService

    async with AsyncSessionLocal() as ledger:
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
                    status, error = "skipped", "Another room-charge run was already in progress."
                else:
                    rows = (await work.execute(
                        select(Admission.id, Admission.ip_number).where(
                            Admission.status.in_([AdmissionStatus.ADMITTED, AdmissionStatus.DISCHARGE_INITIATED])
                        )
                    )).all()
                    service = IPDService(work)
                    posted, failed = 0, []
                    for admission_id, ip_number in rows:
                        try:
                            async with work.begin_nested():
                                charges = await service.accrue_bed_charges(
                                    admission_id,
                                    posted_by_name=AUTOMATIC if triggered_by == "schedule"
                                    else f"Room charges — run by {triggered_by}",
                                )
                            posted += len(charges)
                        except Exception as exc:  # noqa: BLE001 - one admission must not stop the rest
                            logger.exception("room_charge_admission_failed", extra={"ip_number": ip_number})
                            failed.append({"ip_number": ip_number, "error": str(exc)[:300]})
                    summary = {"admissions": len(rows), "charges_posted": posted, "failed": failed}
                    status = "partial" if failed else "done"
    except Exception as exc:  # noqa: BLE001
        logger.exception("room_charge_run_failed")
        error = f"The run stopped: {str(exc)[:300]}"
        status = "failed"

    async with AsyncSessionLocal() as ledger:
        run = await ledger.get(JobRun, run_id)
        run.status, run.summary, run.error, run.finished_at = status, summary, error, _now()
        await ledger.commit()
        await ledger.refresh(run)
    logger.info("room_charge_run", extra={"status": status, **{k: v for k, v in summary.items() if k != "failed"}})
    return run


async def ran_today() -> bool:
    """A finished run today, or one still going that started in the last hour."""
    from app.models.job_run import JobRun

    async with AsyncSessionLocal() as session:
        found = (await session.execute(
            select(JobRun.id).where(
                JobRun.job == JOB,
                JobRun.run_on == local_today(),
                (JobRun.status.in_(["done", "partial"]))
                | ((JobRun.status == "running") & (JobRun.started_at > _now() - timedelta(hours=1))),
            ).limit(1)
        )).first()
    return found is not None


class RoomChargeWorker:
    """Checks every few minutes whether this morning's run is due, and runs it once."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if not settings.BED_CHARGE_WORKER_ENABLED:
            logger.info("room_charge_worker_disabled")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("room_charge_worker_started", extra={"run_at": settings.BED_CHARGE_RUN_AT})

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.BED_CHARGE_CHECK_S)
                if local_now().time() >= run_time() and not await ran_today():
                    await run_room_charges(triggered_by="schedule")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the worker must survive a bad morning
                logger.exception("room_charge_worker_error")


room_charge_worker = RoomChargeWorker()
