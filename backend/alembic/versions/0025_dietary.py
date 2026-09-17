"""Diet modes and date-stamped diet orders against an admission."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_dietary"
down_revision: Union[str, None] = "0024_laboratory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    # Never removed on downgrade: PostgreSQL cannot drop enum values.
    for value in ("diet_order", "diet_stop"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "diet_modes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_nil_by_mouth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_diet_modes_name"),
    )
    op.create_index("ix_diet_modes_code", "diet_modes", ["code"], unique=True)

    op.create_table(
        "diet_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("admission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("diet_modes.id", ondelete="SET NULL")),
        sa.Column("mode_name", sa.String(120), nullable=False),
        sa.Column("is_nil_by_mouth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("instructions", sa.Text()),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("ordered_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("ordered_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("ended_by_name", sa.String(255)),
        sa.Column("end_reason", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_diet_orders_admission_id", "diet_orders", ["admission_id"])
    op.create_index("ix_diet_orders_admission_start", "diet_orders", ["admission_id", "starts_at"])
    # One open order per admission: a new order closes the one before it.
    op.execute("CREATE UNIQUE INDEX uq_diet_orders_open ON diet_orders (admission_id) WHERE ends_at IS NULL")


def downgrade() -> None:
    op.drop_table("diet_orders")
    op.drop_table("diet_modes")
