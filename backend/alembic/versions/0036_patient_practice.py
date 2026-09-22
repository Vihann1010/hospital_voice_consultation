"""Which practice a patient is registered with.

Backfilled from the UHID's first three letters, which is the practice that
issued it. A patient with no UHID (a kiosk walk-in never registered at the
counter) is left empty and belongs to the site's default practice.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_patient_practice"
down_revision: Union[str, None] = "0035_surgery_teeth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("practice", sa.String(3), nullable=True))
    op.create_index("ix_patients_practice", "patients", ["practice"])
    op.execute("UPDATE patients SET practice = substr(uhid, 1, 3) WHERE uhid IS NOT NULL")


def downgrade() -> None:
    op.drop_index("ix_patients_practice", table_name="patients")
    op.drop_column("patients", "practice")
