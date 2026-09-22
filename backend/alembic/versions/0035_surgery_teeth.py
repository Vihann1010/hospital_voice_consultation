"""Which teeth a dental case is for.

The dental form of laterality. Nullable: only a dental booking carries it, and
every surgery booked before dentistry existed has none.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_surgery_teeth"
down_revision: Union[str, None] = "0034_dentistry_department"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("surgeries", sa.Column("teeth", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("surgeries", "teeth")
