"""Patient wallets, and what each payment mode has to record.

Three things arrive together.

**The wallet.** A balance row plus an append-only ledger. The balance is
stored rather than summed on read because spending it has to be serialised —
the row is locked FOR UPDATE while it is debited, which is what makes the
non-negative guarantee real rather than hopeful. The check constraint is the
last line of that defence, in the database where nothing can route around it.

**Two new payment modes.** `cheque`, because the hospital takes them, and
`wallet`, so that money spent from credit is a payment against the bill
without being counted as cash arriving today. Every collection figure filters
`wallet` out for exactly that reason.

**`mode_details`.** One JSON column instead of a dozen mostly-null ones. A
cheque needs a number, a bank and a date; a card needs its last four. The
required set differs per mode and grows whenever the hospital accepts a new
instrument, which is a poor fit for columns and a good one for a validated
document.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_wallet_and_receipts"
down_revision: Union[str, None] = "0011_appointment_callers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WALLET_ENTRY_KIND = ("deposit", "refund_credit", "applied", "withdrawal", "adjustment")
NEW_PAYMENT_MODES = ("cheque", "wallet")
NEW_AUDIT_ACTIONS = ("wallet_deposit", "wallet_withdrawal")


def upgrade() -> None:
    for value in NEW_PAYMENT_MODES:
        op.execute(f"ALTER TYPE payment_mode ADD VALUE IF NOT EXISTS '{value}'")
    for value in NEW_AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    wallet_entry_kind = postgresql.ENUM(
        *WALLET_ENTRY_KIND, name="wallet_entry_kind", create_type=False
    )
    wallet_entry_kind.create(op.get_bind(), checkfirst=True)

    op.add_column("payments", sa.Column("mode_details", postgresql.JSONB()))

    op.create_table(
        "patient_wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("balance_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("balance_paise >= 0", name="ck_wallet_not_negative"),
    )
    op.create_index("ix_patient_wallets_patient_id", "patient_wallets", ["patient_id"])

    op.create_table(
        "wallet_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("patient_wallets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", wallet_entry_kind, nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("balance_after_paise", sa.Integer(), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("invoices.id", ondelete="SET NULL")),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("payments.id", ondelete="SET NULL")),
        sa.Column("receipt_number", sa.String(32)),
        sa.Column("reason", sa.Text()),
        sa.Column("created_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_wallet_entries_wallet_id", "wallet_entries", ["wallet_id"])
    op.create_index("ix_wallet_entries_patient_id", "wallet_entries", ["patient_id"])
    op.create_index("ix_wallet_entries_kind", "wallet_entries", ["kind"])
    op.create_index("ix_wallet_entries_receipt_number", "wallet_entries", ["receipt_number"])
    op.create_index(
        "ix_wallet_entries_patient_time", "wallet_entries", ["patient_id", "created_at"]
    )

    # Print settings for the standalone money receipt, seeded to match the
    # invoice so the two documents leave the printer looking related.
    op.execute(
        """
        INSERT INTO print_settings (id, document_type, watermark_duplicates)
        VALUES (gen_random_uuid(), 'receipt', true)
        ON CONFLICT (document_type) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("wallet_entries")
    op.drop_table("patient_wallets")
    op.execute("DROP TYPE IF EXISTS wallet_entry_kind")
    op.drop_column("payments", "mode_details")
    # The two payment_mode values and two audit actions stay. PostgreSQL
    # cannot drop an enum value, and rebuilding either type to remove them
    # would rewrite the payments and audit tables — destroying history to
    # undo an additive change.
