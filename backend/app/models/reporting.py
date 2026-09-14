"""Which columns a report shows.

The old reports let an administrator hide columns, and staff relied on it:
a counter clerk running the invoice list does not need the GST breakdown, and
a fourteen-column table on a small screen is a table nobody reads.

Stored per report and column rather than as a blob, so a column added to a
report later simply appears with its own default instead of being missing
from a saved layout and silently hidden.
"""
from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReportColumnSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "report_column_settings"
    __table_args__ = (
        UniqueConstraint("report_key", "column_key", name="uq_report_column"),
    )

    report_key: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    column_key: Mapped[str] = mapped_column(String(48), nullable=False)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Lower first. Defaults to the order the report declares.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
