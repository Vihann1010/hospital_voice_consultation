"""Leave from the ward, re-admission links, and a log of scheduled job runs.

A patient on leave is still admitted. Whether the bed is kept decides whether
it is charged: a kept bed is held for them and billed; a released bed is free
for someone else and is not. One open leave per admission, enforced here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_leave_readmission_jobs"
down_revision: Union[str, None] = "0022_patient_files_radiology"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    for value in ("leave_start", "leave_return", "room_charges_run"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "admission_leaves",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("admission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_return_on", sa.Date()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("bed_retained", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("released_bed_label", sa.String(32)),
        sa.Column("released_ward_name", sa.String(120)),
        sa.Column("started_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("returned_at", sa.DateTime(timezone=True)),
        sa.Column("returned_by_name", sa.String(255)),
        sa.Column("return_note", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_admission_leaves_admission", "admission_leaves", ["admission_id", "started_at"])
    op.execute("CREATE UNIQUE INDEX uq_admission_leaves_open ON admission_leaves (admission_id) "
               "WHERE returned_at IS NULL")

    op.add_column("admissions", sa.Column(
        "readmission_of_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("admissions.id", ondelete="SET NULL"), nullable=True))
    op.add_column("admissions", sa.Column("days_since_last_discharge", sa.Integer(), nullable=True))

    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job", sa.String(64), nullable=False),
        sa.Column("run_on", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text()),
        sa.Column("triggered_by", sa.String(255), nullable=False, server_default=""),
        *_timestamps(),
    )
    op.create_index("ix_job_runs_job_day", "job_runs", ["job", "run_on"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_job_day", table_name="job_runs")
    op.drop_table("job_runs")
    op.drop_column("admissions", "days_since_last_discharge")
    op.drop_column("admissions", "readmission_of_id")
    op.execute("DROP INDEX IF EXISTS uq_admission_leaves_open")
    op.drop_index("ix_admission_leaves_admission", table_name="admission_leaves")
    op.drop_table("admission_leaves")
