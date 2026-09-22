"""Onito's six discharge modes, exactly as the pilot hospital uses them.

No admission has ever been discharged through this app — the discharge
wizard hardcoded "routine" and had no selector — so `discharge_type` is
NULL on every row today. Safe to replace the enum's member set outright
rather than layer Onito's terms on top of the old ones.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0032_onito_discharge_types"
down_revision: Union[str, None] = "0031_admission_organisation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_VALUES = ("routine", "against_medical_advice", "transferred_out", "absconded", "death")
NEW_VALUES = ("discharged", "expired", "lama", "dama", "dopr", "referred")


def upgrade() -> None:
    op.execute("ALTER TYPE discharge_type RENAME TO discharge_type_old")
    op.execute(
        "CREATE TYPE discharge_type AS ENUM (" +
        ", ".join(f"'{v}'" for v in NEW_VALUES) + ")"
    )
    op.execute(
        "ALTER TABLE admissions ALTER COLUMN discharge_type TYPE discharge_type "
        "USING discharge_type::text::discharge_type"
    )
    op.execute("DROP TYPE discharge_type_old")


def downgrade() -> None:
    op.execute("ALTER TYPE discharge_type RENAME TO discharge_type_old")
    op.execute(
        "CREATE TYPE discharge_type AS ENUM (" +
        ", ".join(f"'{v}'" for v in OLD_VALUES) + ")"
    )
    op.execute(
        "ALTER TABLE admissions ALTER COLUMN discharge_type TYPE discharge_type "
        "USING discharge_type::text::discharge_type"
    )
    op.execute("DROP TYPE discharge_type_old")
