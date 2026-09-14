"""Consultant and referral-provider masters.

Additive: two new tables, nothing existing altered. The consultant rows the
hospital already implies — the doctors who have logins — are created from the
users table so that no screen has an empty dropdown the moment this lands.

Their appointment length and free-follow-up window are seeded to the values
the system behaved as if it had (fifteen minutes, no free follow-up) rather
than to a guess, so this migration changes no behaviour on its own. The real
numbers are set on the consultant screen afterwards.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_consultants"
down_revision: Union[str, None] = "0006_user_admin_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEPARTMENT = postgresql.ENUM(
    "orthopedics", "gynecology", name="department", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "consultants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("department", DEPARTMENT, nullable=False),
        sa.Column("qualification", sa.String(255)),
        sa.Column("registration_number", sa.String(120)),
        sa.Column("phone_number", sa.String(20)),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("appointment_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("free_follow_up_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consultation_service_code", sa.String(32)),
        sa.Column("payout_share_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consultants_full_name", "consultants", ["full_name"])
    op.create_index("ix_consultants_department", "consultants", ["department"])
    op.create_index("ix_consultants_is_active", "consultants", ["is_active"])
    op.create_index("ix_consultants_user_id", "consultants", ["user_id"])

    op.create_table(
        "referral_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("clinic_name", sa.String(255)),
        sa.Column("phone_number", sa.String(20)),
        sa.Column("city", sa.String(120)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_referral_providers_full_name", "referral_providers", ["full_name"])
    op.create_index("ix_referral_providers_is_active", "referral_providers", ["is_active"])

    # Every doctor who already has a login becomes a consultant, linked to it.
    op.execute(
        """
        INSERT INTO consultants (id, full_name, department, user_id, created_at, updated_at)
        SELECT gen_random_uuid(), u.full_name, u.department, u.id, now(), now()
        FROM users u
        WHERE u.role = 'doctor' AND u.department IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("referral_providers")
    op.drop_table("consultants")
