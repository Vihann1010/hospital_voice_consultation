"""Consultant master parity: sex, display flags, sort order, primary.

sex reuses the existing `gender` Postgres enum (patients already have one);
create_type=False so this doesn't try to create it a second time.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_consultant_master_parity"
down_revision: Union[str, None] = "0033_service_master_parity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consultants",
        sa.Column("sex", postgresql.ENUM(name="gender", create_type=False)),
    )
    op.add_column(
        "consultants",
        sa.Column("display_in_opd", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "consultants",
        sa.Column("display_in_ipd", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "consultants",
        sa.Column("display_in_diagnostics", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
    )
    op.add_column(
        "consultants",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "consultants",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("consultants", "is_primary")
    op.drop_column("consultants", "sort_order")
    op.drop_column("consultants", "display_in_diagnostics")
    op.drop_column("consultants", "display_in_ipd")
    op.drop_column("consultants", "display_in_opd")
    op.drop_column("consultants", "sex")
