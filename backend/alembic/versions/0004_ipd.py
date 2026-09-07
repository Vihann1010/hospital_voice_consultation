"""IPD: wards, beds, admissions, charges, vitals, medications, notes.

Additive only. Nine new tables and nine new enum types; nothing existing is
altered or dropped, so OPD, prescriptions and investigations are untouched and
the migration is safe to apply to a live database.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_ipd"
down_revision: Union[str, None] = "0003_emr_reception_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = [
    "wards",
    "beds",
    "admissions",
    "bed_occupancies",
    "admission_charges",
    "vitals_records",
    "medication_orders",
    "medication_administrations",
    "clinical_notes",
]


def upgrade() -> None:
    # Built from the model metadata so the migration and the ORM cannot drift.
    from app.models.registry import Base

    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    to_create = [
        Base.metadata.tables[name] for name in NEW_TABLES if name not in existing
    ]
    if to_create:
        Base.metadata.create_all(bind=bind, tables=to_create, checkfirst=True)


def downgrade() -> None:
    from app.models.registry import Base

    bind = op.get_bind()
    # Reverse order so dependent tables go first.
    for name in reversed(NEW_TABLES):
        table = Base.metadata.tables.get(name)
        if table is not None:
            table.drop(bind=bind, checkfirst=True)

    for enum_name in (
        "ward_type", "bed_status", "admission_type", "admission_status",
        "discharge_type", "charge_category", "medication_route_ipd",
        "medication_status", "note_type",
    ):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
