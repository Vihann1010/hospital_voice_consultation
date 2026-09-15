"""Admission advances become receipted wallet deposits.

`wallet_entries.admission_id` ties an advance to the stay it was taken for, so
the running bill and the inpatient reports can set it against that stay.
`wallet_entries.mode` records how a deposit was paid: until now every deposit
was counted as cash in the drawer, so an advance paid by UPI made the daily
closing expect money that was never in it. Existing deposits and withdrawals
were all taken as cash at the counter and are marked so.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_admission_advance_receipts"
down_revision: Union[str, None] = "0025_dietary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wallet_entries", sa.Column(
        "admission_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("admissions.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_wallet_entries_admission_id", "wallet_entries", ["admission_id"])
    op.add_column("wallet_entries", sa.Column(
        "mode", postgresql.ENUM(name="payment_mode", create_type=False), nullable=True))
    op.execute("UPDATE wallet_entries SET mode = 'cash' WHERE kind IN ('deposit', 'withdrawal')")


def downgrade() -> None:
    op.drop_column("wallet_entries", "mode")
    op.drop_index("ix_wallet_entries_admission_id", table_name="wallet_entries")
    op.drop_column("wallet_entries", "admission_id")
