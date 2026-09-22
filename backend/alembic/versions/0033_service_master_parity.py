"""Service master parity: IPD rate, unit, flags, per-consultant rates.

The per-organisation half of this (negotiated_rates) already existed from
0014 and turned out to already be wired into the pricing engine — only the
consultant side and these ServiceItem columns were actually missing.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_service_master_parity"
down_revision: Union[str, None] = "0032_onito_discharge_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("service_items", sa.Column("ipd_rate_paise", sa.Integer()))
    op.add_column("service_items", sa.Column("unit", sa.String(32)))
    op.add_column(
        "service_items",
        sa.Column("rate_editable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "service_items",
        sa.Column("discount_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "service_items",
        sa.Column("requires_consultant", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )

    op.create_table(
        "consultant_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consultant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_item_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rate_paise", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("consultant_id", "service_item_id",
                            name="uq_rate_consultant_service"),
    )
    op.create_index("ix_consultant_rates_consultant_id", "consultant_rates",
                    ["consultant_id"])
    op.create_index("ix_consultant_rates_service_item_id", "consultant_rates",
                    ["service_item_id"])


def downgrade() -> None:
    op.drop_index("ix_consultant_rates_service_item_id", table_name="consultant_rates")
    op.drop_index("ix_consultant_rates_consultant_id", table_name="consultant_rates")
    op.drop_table("consultant_rates")

    op.drop_column("service_items", "requires_consultant")
    op.drop_column("service_items", "discount_allowed")
    op.drop_column("service_items", "rate_editable")
    op.drop_column("service_items", "unit")
    op.drop_column("service_items", "ipd_rate_paise")
