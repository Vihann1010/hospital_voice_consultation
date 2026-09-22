"""Dentistry as a fourth department, and dental radiographs as a category.

Smile Dental runs inside the same clinic as CN Gastrocare: one reception, one
patient record, two departments. Only the enum values are added here; the
clinical content lives in app.departments and the modules it names, and the
application refuses to start until all of it is present.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0034_dentistry_department"
down_revision: Union[str, None] = "0033_surgery_visit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE department ADD VALUE IF NOT EXISTS 'dentistry'")
    op.execute("ALTER TYPE investigationcategory ADD VALUE IF NOT EXISTS 'dental'")


def downgrade() -> None:
    # Postgres cannot drop an enum value without rewriting every column that
    # uses the type, and rows may already reference it. Left in place, as
    # with 0031 and 0032.
    pass
