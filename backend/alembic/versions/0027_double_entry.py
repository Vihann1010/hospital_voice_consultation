"""Double-entry books and consultant payouts.

Account groups, ledgers, vouchers with their lines, and payout runs. Also the
service kinds each consultant's share applies to. See app/models/accounts.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_double_entry"
down_revision: Union[str, None] = "0026_admission_advance_receipts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _id():
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _fk(name, target, ondelete, nullable=True):
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    for value in ("voucher_create", "voucher_reverse", "books_posting_run", "payout_approve",
                  "payout_pay", "payout_cancel", "payout_terms"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("consultants", sa.Column(
        "payout_categories", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[\"consultation\"]'::jsonb")))

    op.create_table(
        "account_groups", _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("nature", sa.String(16), nullable=False),
        _fk("parent_id", "account_groups.id", "RESTRICT"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
    )
    op.create_index("ix_account_groups_code", "account_groups", ["code"], unique=True)

    op.create_table(
        "ledgers", _id(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        _fk("group_id", "account_groups.id", "RESTRICT", nullable=False),
        sa.Column("system_key", sa.String(48), unique=True),
        sa.Column("consultant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultants.id", ondelete="RESTRICT"), unique=True),
        sa.Column("opening_balance_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text()),
        *_ts(),
    )
    op.create_index("ix_ledgers_code", "ledgers", ["code"], unique=True)
    op.create_index("ix_ledgers_group_id", "ledgers", ["group_id"])

    op.create_table(
        "vouchers", _id(),
        sa.Column("voucher_number", sa.String(32), nullable=False),
        sa.Column("voucher_type", sa.String(16), nullable=False),
        sa.Column("financial_year", sa.String(8), nullable=False),
        sa.Column("voucher_date", sa.Date(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(32)),
        sa.Column("source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="posted"),
        _fk("reversal_of_id", "vouchers.id", "RESTRICT"),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_by_name", sa.String(255)),
        sa.Column("reversal_reason", sa.Text()),
        _fk("patient_id", "patients.id", "SET NULL"),
        _fk("consultant_id", "consultants.id", "SET NULL"),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_name", sa.String(255), nullable=False, server_default=""),
        *_ts(),
    )
    op.create_index("ix_vouchers_voucher_number", "vouchers", ["voucher_number"], unique=True)
    op.create_index("ix_vouchers_financial_year", "vouchers", ["financial_year"])
    op.create_index("ix_vouchers_voucher_date", "vouchers", ["voucher_date"])
    op.create_index("ix_vouchers_date_type", "vouchers", ["voucher_date", "voucher_type"])
    op.create_index("ix_vouchers_source", "vouchers", ["source_type", "source_id"])
    # One live voucher per source record: running the engine twice posts nothing twice.
    op.execute("CREATE UNIQUE INDEX uq_vouchers_live_source ON vouchers (source_type, source_id) "
               "WHERE status = 'posted' AND reversal_of_id IS NULL AND source_id IS NOT NULL")

    op.create_table(
        "voucher_lines", _id(),
        _fk("voucher_id", "vouchers.id", "CASCADE", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        _fk("ledger_id", "ledgers.id", "RESTRICT", nullable=False),
        sa.Column("debit_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credit_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("narration", sa.Text()),
        *_ts(),
        sa.CheckConstraint("debit_paise >= 0 AND credit_paise >= 0", name="ck_voucher_line_positive"),
        sa.CheckConstraint("(debit_paise = 0) <> (credit_paise = 0)", name="ck_voucher_line_one_side"),
    )
    op.create_index("ix_voucher_lines_voucher_id", "voucher_lines", ["voucher_id"])
    op.create_index("ix_voucher_lines_ledger", "voucher_lines", ["ledger_id"])

    op.create_table(
        "consultant_payouts", _id(),
        sa.Column("payout_number", sa.String(32), nullable=False),
        _fk("consultant_id", "consultants.id", "RESTRICT", nullable=False),
        sa.Column("consultant_name", sa.String(255), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("share_percent", sa.Integer(), nullable=False),
        sa.Column("categories", sa.String(255), nullable=False, server_default=""),
        sa.Column("base_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("share_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tds_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("net_paid_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="approved"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("paid_on", sa.Date()),
        sa.Column("paid_by_name", sa.String(255)),
        sa.Column("payment_mode", sa.String(16)),
        sa.Column("payment_reference", sa.String(120)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by_name", sa.String(255)),
        sa.Column("cancel_reason", sa.Text()),
        _fk("accrual_voucher_id", "vouchers.id", "RESTRICT"),
        _fk("payment_voucher_id", "vouchers.id", "RESTRICT"),
        sa.Column("notes", sa.Text()),
        *_ts(),
    )
    op.create_index("ix_consultant_payouts_payout_number", "consultant_payouts", ["payout_number"], unique=True)
    op.create_index("ix_consultant_payouts_consultant_id", "consultant_payouts", ["consultant_id"])
    op.create_index("ix_consultant_payouts_status", "consultant_payouts", ["status"])

    op.create_table(
        "consultant_payout_items", _id(),
        _fk("payout_id", "consultant_payouts.id", "CASCADE", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(16), nullable=False, server_default="bill"),
        _fk("invoice_id", "invoices.id", "RESTRICT"),
        _fk("payment_id", "payments.id", "RESTRICT"),
        sa.Column("invoice_number", sa.String(32), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("patient_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("eligible_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("base_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("share_paise", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
    )
    op.create_index("ix_consultant_payout_items_payout_id", "consultant_payout_items", ["payout_id"])
    op.create_index("ix_consultant_payout_items_invoice_id", "consultant_payout_items", ["invoice_id"])
    op.create_index("ix_consultant_payout_items_payment_id", "consultant_payout_items", ["payment_id"])


def downgrade() -> None:
    op.drop_table("consultant_payout_items")
    op.drop_table("consultant_payouts")
    op.drop_table("voucher_lines")
    op.drop_table("vouchers")
    op.drop_table("ledgers")
    op.drop_table("account_groups")
    op.drop_column("consultants", "payout_categories")
