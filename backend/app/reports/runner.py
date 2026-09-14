"""Running a report: columns, rows, totals, and a CSV of the same thing.

Written once and shared by all six, so a report author declares its columns
and writes one query, and gets filtering, totalling, column visibility and
export without asking for them.
"""
import csv
import io
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting import ReportColumnSetting
from app.reports.definitions import ColumnType, ReportSpec


async def visible_columns(
    session: AsyncSession, spec: ReportSpec
) -> List[Dict[str, Any]]:
    """The report's columns, with any administrator overrides applied.

    A column with no stored setting keeps the report's own default, so adding
    a column to a report later makes it appear rather than vanish behind a
    saved layout that has never heard of it.
    """
    result = await session.execute(
        select(ReportColumnSetting).where(ReportColumnSetting.report_key == spec.key)
    )
    overrides = {row.column_key: row for row in result.scalars()}

    columns = []
    for index, column in enumerate(spec.columns):
        override = overrides.get(column.key)
        columns.append({
            "key": column.key,
            "label": column.label,
            "type": column.type.value,
            "total": column.total,
            "visible": override.visible if override else column.default_visible,
            "position": override.position if override else index,
        })
    columns.sort(key=lambda item: item["position"])
    return columns


def totals_for(spec: ReportSpec, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Footer figures.

    Summed over every row, including rows the reader has hidden a column for.
    A total that changed when somebody hid a column would be a different
    total, and the footer is what gets copied into the day book.
    """
    return {
        column.key: sum(int(row.get(column.key) or 0) for row in rows)
        for column in spec.columns
        if column.total
    }


async def run(
    session: AsyncSession,
    spec: ReportSpec,
    *,
    date_from: date,
    date_to: date,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    rows = await spec.build(
        session, date_from=date_from, date_to=date_to, user_name=user_name
    )
    return {
        "key": spec.key,
        "title": spec.title,
        "description": spec.description,
        "date_from": date_from,
        "date_to": date_to,
        "scoped_to": user_name,
        "columns": await visible_columns(session, spec),
        "rows": rows,
        "totals": totals_for(spec, rows),
        "row_count": len(rows),
    }


def _cell(value: Any, column_type: str) -> str:
    if value is None:
        return ""
    if column_type == ColumnType.MONEY.value:
        # Plain rupees with two decimals and no symbol or separator: a
        # spreadsheet has to be able to add this column up, and "₹1,234.00"
        # arrives as text.
        return f"{int(value) / 100:.2f}"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def to_csv(report: Dict[str, Any]) -> str:
    """Only the visible columns, in the order they are shown.

    An export that silently included hidden columns would not match the
    screen it was exported from, which is the one thing a person checking a
    figure needs it to do.
    """
    shown = [column for column in report["columns"] if column["visible"]]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([column["label"] for column in shown])
    for row in report["rows"]:
        writer.writerow([_cell(row.get(c["key"]), c["type"]) for c in shown])

    totals = report.get("totals") or {}
    if totals:
        writer.writerow([])
        writer.writerow(
            [
                "TOTAL" if index == 0
                else _cell(totals.get(column["key"]), column["type"])
                if column["key"] in totals
                else ""
                for index, column in enumerate(shown)
            ]
        )
    return buffer.getvalue()
