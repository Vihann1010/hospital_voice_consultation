"""TPA and insurance claims.

Links policies and claims to the payer in the organisation register and claims
to the admission; records the pre-authorisation amounts, the share booked to
the bill, and the payer's settlements. See app/insurance/rules.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_tpa_claims"
down_revision: Union[str, None] = "0027_double_entry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk(name, target, ondelete):
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete), nullable=True)


def upgrade() -> None:
    for value in ("policy_save", "claim_create", "claim_status", "claim_book", "claim_unbook",
                  "claim_settle", "claim_settle_cancel", "consultant_save"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("insurance_policies", _fk("organisation_id", "organisations.id", "SET NULL"))
    op.create_index("ix_insurance_policies_organisation_id", "insurance_policies", ["organisation_id"])

    op.add_column("insurance_claims", _fk("organisation_id", "organisations.id", "SET NULL"))
    op.add_column("insurance_claims", _fk("admission_id", "admissions.id", "SET NULL"))
    op.add_column("insurance_claims", _fk("booking_payment_id", "payments.id", "SET NULL"))
    for column in ("pre_auth_requested_paise", "pre_auth_approved_paise", "booked_paise"):
        op.add_column("insurance_claims", sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("insurance_claims", sa.Column("payer_name", sa.String(255), nullable=False, server_default=""))
    op.add_column("insurance_claims", sa.Column("created_by_name", sa.String(255), nullable=False,
                                                server_default=""))
    op.create_index("ix_insurance_claims_organisation_id", "insurance_claims", ["organisation_id"])
    op.create_index("ix_insurance_claims_admission_id", "insurance_claims", ["admission_id"])

    op.create_table(
        "claim_settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("insurance_claims.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("received_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tds_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deduction_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deduction_reason", sa.Text()),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("reference", sa.String(120)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by_name", sa.String(255)),
        sa.Column("cancel_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "received_paise >= 0 AND tds_paise >= 0 AND deduction_paise >= 0 "
            "AND received_paise + tds_paise + deduction_paise > 0",
            name="ck_claim_settlement_amounts",
        ),
    )
    op.create_index("ix_claim_settlements_claim_id", "claim_settlements", ["claim_id"])
    op.create_index("ix_claim_settlements_received_on", "claim_settlements", ["received_on"])


def downgrade() -> None:
    op.drop_table("claim_settlements")
    op.drop_index("ix_insurance_claims_admission_id", table_name="insurance_claims")
    op.drop_index("ix_insurance_claims_organisation_id", table_name="insurance_claims")
    for column in ("created_by_name", "payer_name", "booked_paise", "pre_auth_approved_paise",
                   "pre_auth_requested_paise", "booking_payment_id", "admission_id", "organisation_id"):
        op.drop_column("insurance_claims", column)
    op.drop_index("ix_insurance_policies_organisation_id", table_name="insurance_policies")
    op.drop_column("insurance_policies", "organisation_id")
