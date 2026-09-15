"""Reporting: one shape, six reports, and everything around them written once."""
from app.reports import opd  # noqa: F401  (registers the reports on import)
from app.reports import theatre  # noqa: F401
from app.reports import lab  # noqa: F401
from app.reports import diet  # noqa: F401
from app.reports import accounts  # noqa: F401
from app.reports import books  # noqa: F401
from app.reports import insurance  # noqa: F401
from app.reports.definitions import (  # noqa: F401
    Column,
    ColumnType,
    ReportSpec,
    catalogue,
    get,
)
