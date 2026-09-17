"""One run of a scheduled job, kept so that "did the room charges go on last
night?" has an answer that is not a log file."""
from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "job_runs"

    job: Mapped[str] = mapped_column(String(64), nullable=False)
    run_on: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    #: running | done | partial | skipped | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
