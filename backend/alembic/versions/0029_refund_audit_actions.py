"""Audit actions for refunds and bill cancellations.

Both were recorded as "export_document", so neither could be found by
searching the audit trail for what actually happened.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029_refund_audit_actions"
down_revision: Union[str, None] = "0028_tpa_claims"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for value in ("refund_issue", "invoice_cancel"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # A value cannot be removed from a Postgres enum without rewriting it, and
    # rows already reference these; left in place deliberately.
    pass
