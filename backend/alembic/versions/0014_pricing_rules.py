"""Negotiated rates, and the consultant settings that finally get applied.

Two of these columns already existed and did nothing. `free_follow_up_days`
and `consultation_service_code` have been on the consultant register since
Part 1 — editable, printed in the master screen, and read by no code at all.
This migration is what makes them mean something, together with the pricing
engine in app/billing/pricing.py.

The organisation table replaces free-text insurer names on the policy. The
same employer covers hundreds of patients under one rate card, and "what did
we agree with them" is unanswerable while the answer is retyped per patient.

`pricing_notes` is stored on the invoice rather than recomputed. Rates and
follow-up windows change; a bill has to keep explaining itself afterwards.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_pricing_rules"
down_revision: Union[str, None] = "0013_corrections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consultants",
        sa.Column("first_consultation_free", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )

    op.create_table(
        "organisations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("payer_type", postgresql.ENUM(name="payer_type", create_type=False),
                  nullable=False, server_default="corporate"),
        sa.Column("contact_person", sa.String(255)),
        sa.Column("phone_number", sa.String(20)),
        sa.Column("email", sa.String(255)),
        sa.Column("address", sa.Text()),
        sa.Column("default_discount_percent", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("credit_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_organisations_code", "organisations", ["code"])
    op.create_index("ix_organisations_name", "organisations", ["name"])
    op.create_index("ix_organisations_is_active", "organisations", ["is_active"])

    op.create_table(
        "negotiated_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_item_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rate_paise", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("organisation_id", "service_item_id",
                            name="uq_rate_org_service"),
    )
    op.create_index("ix_negotiated_rates_organisation_id", "negotiated_rates",
                    ["organisation_id"])
    op.create_index("ix_negotiated_rates_service_item_id", "negotiated_rates",
                    ["service_item_id"])

    op.add_column(
        "invoices",
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="SET NULL")),
    )
    op.create_index("ix_invoices_organisation_id", "invoices", ["organisation_id"])
    op.add_column("invoices", sa.Column("pricing_notes", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("invoices", "pricing_notes")
    op.drop_index("ix_invoices_organisation_id", table_name="invoices")
    op.drop_column("invoices", "organisation_id")
    op.drop_table("negotiated_rates")
    op.drop_table("organisations")
    op.drop_column("consultants", "first_consultation_free")
