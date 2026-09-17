"""A remark against each charge.

The counter often has to say why one line reads as it does — "second sitting",
"as advised by Dr Agarwal", "dressing material charged separately". Until now
that could only be written against the whole bill, so a bill with six lines
carried one sentence that explained none of them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_invoice_line_remark"
down_revision: Union[str, None] = "0029_refund_audit_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoice_lines", sa.Column("remark", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice_lines", "remark")
