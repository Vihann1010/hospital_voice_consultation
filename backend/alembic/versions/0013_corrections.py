"""Cancelling, uncancelling and amending counter work.

Four additions, each answering a question the previous schema could not.

**A receipt can be cancelled without being refunded.** The two were the same
thing before, and they are not: a refund means money went back to the patient,
a cancellation means the entry was a mistake and no money moved. Recording a
keying error as a refund shows the hospital paying out cash it never paid.

**A registration can be cancelled.** `VisitStatus.CANCELLED` already existed;
nothing recorded when or why.

**A bill carries an amendment trail.** A bill corrected three times before the
patient paid should be visible as such, rather than quietly differing from the
one they were shown ten minutes ago.

**A bill can be locked by a payout.** Nothing sets `payout_locked_at` yet — the
consultant payout run arrives in Part 5. The column and its guard land now so
every correction path is written to respect it from the start, instead of each
one having to be found and patched later.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_corrections"
down_revision: Union[str, None] = "0012_wallet_and_receipts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_AUDIT_ACTIONS = (
    "receipt_cancel",
    "invoice_uncancel",
    "invoice_amend",
    "visit_cancel",
    "visit_uncancel",
)


def upgrade() -> None:
    for value in NEW_AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("payments", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("payments", sa.Column("cancellation_reason", sa.Text()))
    op.add_column("payments", sa.Column("cancelled_by_name", sa.String(255)))

    op.add_column("invoices", sa.Column("amended_at", sa.DateTime(timezone=True)))
    op.add_column("invoices", sa.Column("amendment_reason", sa.Text()))
    op.add_column(
        "invoices",
        sa.Column("amendment_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("invoices", sa.Column("payout_locked_at", sa.DateTime(timezone=True)))

    op.add_column("visits", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("visits", sa.Column("cancellation_reason", sa.Text()))


def downgrade() -> None:
    op.drop_column("visits", "cancellation_reason")
    op.drop_column("visits", "cancelled_at")
    op.drop_column("invoices", "payout_locked_at")
    op.drop_column("invoices", "amendment_count")
    op.drop_column("invoices", "amendment_reason")
    op.drop_column("invoices", "amended_at")
    op.drop_column("payments", "cancelled_by_name")
    op.drop_column("payments", "cancellation_reason")
    op.drop_column("payments", "cancelled_at")
    # The audit_action values stay: PostgreSQL cannot drop an enum value, and
    # rebuilding the type would rewrite the audit table.
