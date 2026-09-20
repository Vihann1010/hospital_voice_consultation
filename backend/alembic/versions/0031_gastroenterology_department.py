"""Gastroenterology as a third department.

The platform was built for two departments and the code assumed it: anything
that was not orthopedics was treated as gynecology. Adding the enum value is
the small half of that change; the code that now looks each department up
explicitly, and raises when one is unconfigured, is the rest.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0031_gastroenterology_department"
down_revision: Union[str, None] = "0030_invoice_line_remark"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE department ADD VALUE IF NOT EXISTS 'gastroenterology'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum type without rewriting it and
    # every column that uses it — sixteen tables here — and rows may already
    # reference it. Left in place deliberately.
    pass
