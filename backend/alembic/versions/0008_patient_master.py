"""Widen the patient record, and let the hospital decide which fields it asks for.

Every new column is nullable. Existing patients keep exactly the data they
have, and the counter is not forced to backfill an occupation for forty
thousand people before it can register the next one.

The field settings are seeded so the registration form on day one asks for
what it asks for today — name, age, sex and mobile required, the rest
optional — rather than suddenly demanding twenty fields. Anything the hospital
does not want is switched to hidden on the settings screen afterwards.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_patient_master"
down_revision: Union[str, None] = "0007_consultants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = [
    ("title", sa.String(16)),
    ("guardian_relation", sa.String(16)),
    ("guardian_name", sa.String(255)),
    ("email", sa.String(255)),
    ("govt_id_type", sa.String(32)),
    ("govt_id_number", sa.String(64)),
    ("state", sa.String(120)),
    ("country", sa.String(120)),
    ("pincode", sa.String(12)),
    ("religion", sa.String(64)),
    ("marital_status", sa.String(32)),
    ("nationality", sa.String(64)),
    ("occupation", sa.String(120)),
    ("category", sa.String(64)),
    ("group_one", sa.String(64)),
    ("group_two", sa.String(64)),
]

# field_key, visibility, display_order. Mirrors what the counter fills in
# today, so nothing about registration changes until someone changes it.
SEED = [
    ("title", "optional", 10),
    ("name", "required", 20),
    ("guardian_relation", "optional", 30),
    ("guardian_name", "optional", 40),
    ("age", "required", 50),
    ("date_of_birth", "optional", 60),
    ("gender", "required", 70),
    ("phone_number", "required", 80),
    ("email", "optional", 90),
    ("emergency_contact_name", "optional", 100),
    ("emergency_contact_phone", "optional", 110),
    ("govt_id_type", "optional", 120),
    ("govt_id_number", "optional", 130),
    ("address", "optional", 140),
    ("city", "optional", 150),
    ("state", "optional", 160),
    ("pincode", "optional", 170),
    ("country", "hidden", 180),
    ("blood_group", "optional", 190),
    ("marital_status", "optional", 200),
    ("occupation", "optional", 210),
    ("religion", "hidden", 220),
    ("nationality", "hidden", 230),
    ("category", "optional", 240),
    ("group_one", "hidden", 250),
    ("group_two", "hidden", 260),
]


def upgrade() -> None:
    for name, kind in NEW_COLUMNS:
        op.add_column("patients", sa.Column(name, kind, nullable=True))
    op.create_index("ix_patients_category", "patients", ["category"])

    op.create_table(
        "patient_field_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("field_key", sa.String(64), nullable=False, unique=True),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="optional"),
        sa.Column("label", sa.String(120)),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_patient_field_settings_field_key", "patient_field_settings", ["field_key"]
    )

    settings = sa.table(
        "patient_field_settings",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("field_key", sa.String),
        sa.column("visibility", sa.String),
        sa.column("display_order", sa.Integer),
    )
    op.execute(
        settings.insert().from_select(
            ["id", "field_key", "visibility", "display_order"],
            sa.select(
                sa.func.gen_random_uuid(),
                sa.column("field_key"),
                sa.column("visibility"),
                sa.column("display_order"),
            ).select_from(
                sa.values(
                    sa.column("field_key", sa.String),
                    sa.column("visibility", sa.String),
                    sa.column("display_order", sa.Integer),
                    name="seed",
                ).data(SEED)
            ),
        )
    )


def downgrade() -> None:
    op.drop_table("patient_field_settings")
    op.drop_index("ix_patients_category", table_name="patients")
    for name, _ in reversed(NEW_COLUMNS):
        op.drop_column("patients", name)
