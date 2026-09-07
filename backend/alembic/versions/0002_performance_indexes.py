"""Indexes for the queries the dashboard actually runs.

Found by auditing the ORDER BY and WHERE clauses in the repositories against
the declared indexes. Every index here backs a query on a hot path:

  consultations (started_at DESC)        every queue and list view sorts by it
  consultations (department, status)     the dashboard's primary filter pair
  consultations (patient_id, started_at) the patient visit timeline
  prescriptions (patient_id, created_at) the prescription list
  reports       (patient_id, created_at) the report list
  orders        (patient_id, created_at) the investigation list

Created CONCURRENTLY so applying them to a live database does not lock writes.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0002_performance_indexes"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# CONCURRENTLY cannot run inside a transaction block.
INDEXES = [
    ("ix_consultations_started_at_desc", "consultations", "(started_at DESC)"),
    ("ix_consultations_dept_status", "consultations", "(department, status)"),
    ("ix_consultations_patient_started", "consultations", "(patient_id, started_at DESC)"),
    ("ix_patients_phone", "patients", "(phone_number)"),
    ("ix_prescriptions_patient_created", "prescriptions", "(patient_id, created_at DESC)"),
    ("ix_prescriptions_dept_status", "prescriptions", "(department, status)"),
    ("ix_reports_patient_created", "investigation_reports", "(patient_id, created_at DESC)"),
    ("ix_reports_group_version", "investigation_reports", "(group_id, version DESC)"),
    ("ix_orders_patient_created", "investigation_orders", "(patient_id, created_at DESC)"),
    ("ix_deliveries_retry_due", "message_deliveries", "(next_retry_at) WHERE next_retry_at IS NOT NULL"),
]


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa_text("COMMIT"))
    for name, table, definition in INDEXES:
        connection.execute(
            sa_text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {definition}")
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa_text("COMMIT"))
    for name, _, _ in INDEXES:
        connection.execute(sa_text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
