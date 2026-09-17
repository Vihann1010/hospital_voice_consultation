"""The in-house laboratory: masters, tests with their parameters, requests and results.

See `app/models/lab.py` for why results are stored as a snapshot per test.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_laboratory"
down_revision: Union[str, None] = "0023_leave_readmission_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _uuid(name, target, ondelete, nullable=True):
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete),
                     nullable=nullable)


def _json_list(name):
    return sa.Column(name, postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb"))


def upgrade() -> None:
    # Never removed on downgrade: PostgreSQL cannot drop enum values.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'lab'")
    for value in ("lab_register", "lab_verify", "lab_reopen", "lab_cancel"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "lab_masters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(32)),
        sa.Column("category", sa.String(64)),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("kind", "name", name="uq_lab_master_kind_name"),
    )
    op.create_index("ix_lab_masters_kind", "lab_masters", ["kind"])

    op.create_table(
        "lab_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("group_name", sa.String(64), nullable=False, server_default="General"),
        sa.Column("specimen", sa.String(120)),
        sa.Column("service_code", sa.String(32)),
        sa.Column("catalog_code", sa.String(64)),
        sa.Column("is_culture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("turnaround_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("interpretation", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ranges_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("ranges_reviewed_by_name", sa.String(255)),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_lab_tests_code", "lab_tests", ["code"], unique=True)
    op.create_index("ix_lab_tests_name", "lab_tests", ["name"])
    op.create_index("ix_lab_tests_catalog_code", "lab_tests", ["catalog_code"])

    op.create_table(
        "lab_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _uuid("test_id", "lab_tests.id", "CASCADE", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("analyte_key", sa.String(64)),
        _json_list("aliases"),
        sa.Column("result_type", sa.String(16), nullable=False, server_default="numeric"),
        sa.Column("unit", sa.String(32)),
        sa.Column("method", sa.String(120)),
        _json_list("choices"),
        _json_list("normal_values"),
        _json_list("ranges"),
        sa.Column("range_text", sa.String(255)),
        sa.Column("print_default", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_lab_parameters_test_id", "lab_parameters", ["test_id"])

    op.create_table(
        "lab_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_number", sa.String(32), nullable=False),
        _uuid("patient_id", "patients.id", "RESTRICT", nullable=False),
        _uuid("admission_id", "admissions.id", "SET NULL"),
        _uuid("consultation_id", "consultations.id", "SET NULL"),
        _uuid("order_id", "investigation_orders.id", "SET NULL"),
        _uuid("invoice_id", "invoices.id", "SET NULL"),
        sa.Column("billing", sa.String(16), nullable=False, server_default="invoice"),
        sa.Column("status", sa.String(24), nullable=False, server_default="registered"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="routine"),
        sa.Column("referred_by", sa.String(255)),
        _uuid("consultant_id", "consultants.id", "SET NULL"),
        sa.Column("clinical_notes", sa.Text()),
        _uuid("registered_by_id", "users.id", "SET NULL"),
        sa.Column("registered_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("sample_collected_at", sa.DateTime(timezone=True)),
        sa.Column("sample_collected_by_name", sa.String(255)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.Text()),
        sa.Column("cancelled_by_name", sa.String(255)),
        *_timestamps(),
    )
    op.create_index("ix_lab_requests_lab_number", "lab_requests", ["lab_number"], unique=True)
    op.create_index("ix_lab_requests_patient_id", "lab_requests", ["patient_id"])
    op.create_index("ix_lab_requests_admission_id", "lab_requests", ["admission_id"])
    op.create_index("ix_lab_requests_order_id", "lab_requests", ["order_id"])
    op.create_index("ix_lab_requests_invoice_id", "lab_requests", ["invoice_id"])
    op.create_index("ix_lab_requests_status_created", "lab_requests", ["status", "created_at"])

    op.create_table(
        "lab_request_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _uuid("request_id", "lab_requests.id", "CASCADE", nullable=False),
        _uuid("test_id", "lab_tests.id", "SET NULL"),
        _uuid("order_item_id", "investigation_order_items.id", "SET NULL"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("group_name", sa.String(64), nullable=False, server_default="General"),
        sa.Column("specimen", sa.String(120)),
        sa.Column("is_culture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("unit_rate_paise", sa.Integer(), nullable=False, server_default="0"),
        _uuid("charge_id", "admission_charges.id", "SET NULL"),
        sa.Column("status", sa.String(16), nullable=False, server_default="registered"),
        _json_list("results"),
        sa.Column("culture", postgresql.JSONB()),
        sa.Column("remarks", sa.Text()),
        sa.Column("critical_note", sa.Text()),
        sa.Column("entered_at", sa.DateTime(timezone=True)),
        sa.Column("entered_by_name", sa.String(255)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        _uuid("verified_by_id", "users.id", "SET NULL"),
        sa.Column("verified_by_name", sa.String(255)),
        sa.Column("verifier_qualification", sa.String(255)),
        sa.Column("verifier_registration", sa.String(120)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _json_list("amendments"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.Text()),
        sa.Column("cancelled_by_name", sa.String(255)),
        *_timestamps(),
    )
    op.create_index("ix_lab_request_items_request_id", "lab_request_items", ["request_id"])
    op.create_index("ix_lab_request_items_test_id", "lab_request_items", ["test_id"])
    op.create_index("ix_lab_request_items_order_item_id", "lab_request_items", ["order_item_id"])
    op.create_index("ix_lab_request_items_status", "lab_request_items", ["status"])
    op.create_index("ix_lab_request_items_verified_at", "lab_request_items", ["verified_at"])


def downgrade() -> None:
    op.drop_table("lab_request_items")
    op.drop_table("lab_requests")
    op.drop_table("lab_parameters")
    op.drop_table("lab_tests")
    op.drop_table("lab_masters")
