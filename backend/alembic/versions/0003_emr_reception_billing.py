"""EMR: UHID, visits, billing, finance and insurance.

Adds the reception and billing layer. Two kinds of change here:

* **New tables** — visits, invoices, payments and the rest. Safe.
* **New columns on `patients`** — uhid and demographics. All nullable, so
  existing rows remain valid; the backfill of UHIDs for pre-existing patients
  is a separate, explicit step (scripts/backfill_uhids.py) rather than
  something hidden inside a migration, because it writes patient-visible
  identifiers and should be run deliberately.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_emr_reception_billing"
down_revision: Union[str, None] = "0002_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TABLES = [
    "document_counters",
    "service_items",
    "visits",
    "invoices",
    "invoice_lines",
    "payments",
    "cash_sessions",
    "insurance_policies",
    "insurance_claims",
]

PATIENT_COLUMNS = [
    ("uhid", sa.String(16)),
    ("date_of_birth", sa.Date()),
    ("address", sa.String(512)),
    ("city", sa.String(120)),
    ("blood_group", sa.String(8)),
    ("emergency_contact_name", sa.String(255)),
    ("emergency_contact_phone", sa.String(20)),
    ("legacy_id", sa.String(64)),
]


def upgrade() -> None:
    # The models are the single source of truth for these tables, so creating
    # from metadata guarantees the migration and the ORM cannot drift apart.
    from app.models.registry import Base

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_patient_columns = {
        column["name"] for column in inspector.get_columns("patients")
    }
    for name, column_type in PATIENT_COLUMNS:
        if name not in existing_patient_columns:
            op.add_column("patients", sa.Column(name, column_type, nullable=True))

    # Unique but nullable: migrated rows may not have a UHID yet, and NULLs do
    # not collide in a Postgres unique index.
    existing_indexes = {index["name"] for index in inspector.get_indexes("patients")}
    if "ix_patients_uhid" not in existing_indexes:
        op.create_index("ix_patients_uhid", "patients", ["uhid"], unique=True)
    if "ix_patients_legacy_id" not in existing_indexes:
        op.create_index("ix_patients_legacy_id", "patients", ["legacy_id"])

    tables = set(inspector.get_table_names())
    to_create = [
        Base.metadata.tables[name] for name in NEW_TABLES if name not in tables
    ]
    if to_create:
        Base.metadata.create_all(bind=bind, tables=to_create, checkfirst=True)


def downgrade() -> None:
    from app.models.registry import Base

    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        table = Base.metadata.tables.get(name)
        if table is not None:
            table.drop(bind=bind, checkfirst=True)

    op.drop_index("ix_patients_legacy_id", table_name="patients")
    op.drop_index("ix_patients_uhid", table_name="patients")
    for name, _ in PATIENT_COLUMNS:
        op.drop_column("patients", name)
