"""The operation theatre: rooms, the operation list, surgeries, and theatre notes.

See `app/models/theatre.py` for why the operation name, surgeon and room are
copied onto each surgery rather than only referenced.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_theatre"
down_revision: Union[str, None] = "0019_inpatient_record"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS = postgresql.ENUM("scheduled", "in_theatre", "completed", "cancelled", name="surgery_status")


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    ]


def _department():
    return postgresql.ENUM(name="department", create_type=False)


def upgrade() -> None:
    # Booking, cancelling and the theatre times are audited under their own
    # names. Never removed on downgrade: PostgreSQL cannot drop enum values.
    for value in ("surgery_book", "surgery_cancel", "surgery_time"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    _STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "theatre_rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_theatre_rooms_code", "theatre_rooms", ["code"], unique=True)

    op.create_table(
        "operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("department", _department(), nullable=True),
        sa.Column("grade", sa.String(16), nullable=True),
        sa.Column("default_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("service_code", sa.String(32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_operations_code", "operations", ["code"], unique=True)
    op.create_index("ix_operations_name", "operations", ["name"])

    op.create_table(
        "surgeries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ot_number", sa.String(32), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("admission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admissions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department", _department(), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("operations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operation_name", sa.String(255), nullable=False),
        sa.Column("laterality", sa.String(24), nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("surgeon_consultant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("surgeon_name", sa.String(255), nullable=False),
        sa.Column("assistants", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("anaesthetist_name", sa.String(255), nullable=True),
        sa.Column("anaesthesia_type", sa.String(48), nullable=True),
        sa.Column("room_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("theatre_rooms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("room_name", sa.String(120), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="elective"),
        sa.Column("status", postgresql.ENUM(name="surgery_status", create_type=False),
                  nullable=False, server_default="scheduled"),
        sa.Column("wheel_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anaesthesia_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("incision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wheel_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("booked_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("charge_reference", sa.String(64), nullable=True),
        *_timestamps(),
    )
    for name, columns, unique in (
        ("ix_surgeries_ot_number", ["ot_number"], True),
        ("ix_surgeries_patient_id", ["patient_id"], False),
        ("ix_surgeries_admission_id", ["admission_id"], False),
        ("ix_surgeries_scheduled_at", ["scheduled_at"], False),
        ("ix_surgeries_status", ["status"], False),
        ("ix_surgeries_room_time", ["room_id", "scheduled_at"], False),
        ("ix_surgeries_status_time", ["status", "scheduled_at"], False),
    ):
        op.create_index(name, "surgeries", columns, unique=unique)

    # Theatre notes are pad documents that belong to a surgery.
    op.add_column(
        "pad_documents",
        sa.Column("surgery_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("surgeries.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_pad_documents_surgery_id", "pad_documents", ["surgery_id"])
    # One draft of each theatre note per surgery, however many people open it.
    op.execute(
        "CREATE UNIQUE INDEX uq_pad_documents_surgery_draft ON pad_documents "
        "(surgery_id, document_type) WHERE status = 'draft' AND surgery_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_pad_documents_surgery_draft")
    op.drop_index("ix_pad_documents_surgery_id", table_name="pad_documents")
    op.drop_column("pad_documents", "surgery_id")
    op.drop_table("surgeries")
    op.drop_table("operations")
    op.drop_table("theatre_rooms")
    _STATUS.drop(op.get_bind(), checkfirst=True)
