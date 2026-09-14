"""Appointments, the queue board, and the OPD hours the scheduler needs.

Three things arrive together because none of them is useful alone: a booking
has nowhere to sit without the consultant's hours, and neither is auditable
without the two new actions.

The partial unique index is the part worth reading. The service serialises
booking on the consultant row, which is what actually prevents an overlap;
the index is the backstop for the exact-start case, and it excludes cancelled
rows deliberately — a cancelled booking must not keep holding its slot.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_appointments"
down_revision: Union[str, None] = "0009_print_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPOINTMENT_STATUS = ("pending", "waiting", "engaged", "done", "cancelled")
NEW_AUDIT_ACTIONS = ("appointment_book", "appointment_cancel")


def upgrade() -> None:
    # PostgreSQL will not let a value be added to an enum inside a
    # transaction that then uses it, but ADD VALUE alone is fine here because
    # nothing in this migration writes an audit row.
    for value in NEW_AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    appointment_status = postgresql.ENUM(
        *APPOINTMENT_STATUS, name="appointment_status", create_type=False
    )
    appointment_status.create(op.get_bind(), checkfirst=True)

    # --- when each consultant actually sits ---------------------------------
    op.add_column(
        "consultants",
        sa.Column("opd_start_time", sa.Time(), nullable=False,
                  server_default=sa.text("'09:00:00'")),
    )
    op.add_column(
        "consultants",
        sa.Column("opd_end_time", sa.Time(), nullable=False,
                  server_default=sa.text("'17:00:00'")),
    )
    # Monday to Saturday. An Indian OPD runs six days, so that is the default
    # a new consultant inherits rather than a five-day week nobody works.
    op.add_column(
        "consultants",
        sa.Column("opd_days", sa.String(20), nullable=False,
                  server_default="1,2,3,4,5,6"),
    )

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consultant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consultant_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("department",
                  postgresql.ENUM(name="department", create_type=False), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("status", appointment_status, nullable=False, server_default="pending"),
        sa.Column("visit_type",
                  postgresql.ENUM(name="visit_type", create_type=False), nullable=False,
                  server_default="new"),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("visits.id", ondelete="SET NULL"), unique=True),
        sa.Column("reason", sa.Text()),
        sa.Column("referred_by", sa.String(255)),
        sa.Column("booked_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_scheduled_start", "appointments", ["scheduled_start"])
    op.create_index("ix_appointments_status", "appointments", ["status"])
    op.create_index("ix_appointments_visit_id", "appointments", ["visit_id"])
    op.create_index(
        "ix_appointments_consultant_start", "appointments",
        ["consultant_id", "scheduled_start"],
    )
    op.create_index(
        "ix_appointments_start_status", "appointments", ["scheduled_start", "status"]
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_appointment_consultant_slot "
        "ON appointments (consultant_id, scheduled_start) "
        "WHERE status <> 'cancelled'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_appointment_consultant_slot")
    op.drop_table("appointments")
    op.execute("DROP TYPE IF EXISTS appointment_status")
    op.drop_column("consultants", "opd_days")
    op.drop_column("consultants", "opd_end_time")
    op.drop_column("consultants", "opd_start_time")
    # The two audit_action values stay. PostgreSQL cannot drop an enum value,
    # and rebuilding the type to remove them would rewrite the audit table —
    # a destructive act to undo an additive change.
