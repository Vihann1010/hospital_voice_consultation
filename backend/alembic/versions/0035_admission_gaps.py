"""IPD reception gaps, part 1: attendant address, other consultant."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_admission_gaps"
down_revision: Union[str, None] = "0034_consultant_master_parity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("admissions", sa.Column("attendant_address", sa.Text()))
    op.add_column("admissions", sa.Column("other_consultant_name", sa.String(255)))


def downgrade() -> None:
    op.drop_column("admissions", "other_consultant_name")
    op.drop_column("admissions", "attendant_address")
