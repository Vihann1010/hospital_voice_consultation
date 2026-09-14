"""Which columns each report shows.

The old reports let an administrator hide columns and staff relied on it: a
counter clerk running the invoice list does not need the GST breakdown, and a
fourteen-column table on a small screen is a table nobody reads.

Stored per report and column rather than as one saved layout per report, so a
column added later appears with its own default instead of being absent from
a stored layout and therefore silently hidden.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_report_columns"
down_revision: Union[str, None] = "0015_invoice_consultant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_column_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_key", sa.String(48), nullable=False),
        sa.Column("column_key", sa.String(48), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("report_key", "column_key", name="uq_report_column"),
    )
    op.create_index("ix_report_column_settings_report_key",
                    "report_column_settings", ["report_key"])


def downgrade() -> None:
    op.drop_table("report_column_settings")
