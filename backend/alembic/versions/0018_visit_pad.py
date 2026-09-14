"""The Visit Pad: layouts, documents, templates and the suggestion catalogue.

The configurable document engine every clinical screen in Part 3 is built on.
See `app/models/pad.py` for why each table exists and why document types are
strings rather than a database enum.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_visit_pad"
down_revision: Union[str, None] = "0017_report_document_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS = postgresql.ENUM("draft", "signed", "superseded", name="pad_status")


def _department():
    # The department type already exists; this only refers to it.
    return postgresql.ENUM(name="department", create_type=False)


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    # Signing, amending and layout changes are audited under their own names.
    # Added first, and never removed on downgrade: PostgreSQL cannot drop an
    # enum value, and audit rows may already carry them.
    for value in ("pad_sign", "pad_amend", "pad_layout_change"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    _STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "pad_layouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_type", sa.String(48), nullable=False),
        sa.Column("department", _department(), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("sections", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_name", sa.String(255), nullable=False, server_default=""),
        *_timestamps(),
    )
    op.create_index("ix_pad_layouts_document_type", "pad_layouts", ["document_type"])
    op.create_index("ix_pad_layouts_owner_id", "pad_layouts", ["owner_id"])
    op.create_index("ix_pad_layouts_scope", "pad_layouts",
                    ["document_type", "department", "owner_id"])
    # One layout per scope. NULLs would otherwise count as distinct, and two
    # "hospital-wide" layouts for the same document would leave it a coin toss
    # which one a doctor sees. NULLS NOT DISTINCT (PostgreSQL 15+) says so on
    # the columns themselves; the obvious coalesce(department::text, '') is
    # refused, because an enum-to-text cast is not immutable.
    op.execute(
        "CREATE UNIQUE INDEX uq_pad_layouts_scope ON pad_layouts "
        "(document_type, department, owner_id) NULLS NOT DISTINCT"
    )

    op.create_table(
        "pad_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_type", sa.String(48), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("admission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admissions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department", _department(), nullable=True),
        sa.Column("layout_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pad_layouts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("layout_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sections", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("values", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("provenance", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", postgresql.ENUM(name="pad_status", create_type=False),
                  nullable=False, server_default="draft"),
        sa.Column("author_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("signed_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signed_by_name", sa.String(255), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pad_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amendment_reason", sa.Text(), nullable=True),
        sa.Column("print_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    for name, columns in (
        ("ix_pad_documents_document_type", ["document_type"]),
        ("ix_pad_documents_patient_id", ["patient_id"]),
        ("ix_pad_documents_consultation_id", ["consultation_id"]),
        ("ix_pad_documents_admission_id", ["admission_id"]),
        ("ix_pad_documents_status", ["status"]),
        ("ix_pad_documents_patient_type", ["patient_id", "document_type", "created_at"]),
        ("ix_pad_documents_group", ["group_id", "version"]),
    ):
        op.create_index(name, "pad_documents", columns)
    # At most one live draft per consultation and document type. Two doctors
    # opening the same patient's pad must land on one draft, not fork it.
    op.execute(
        "CREATE UNIQUE INDEX uq_pad_documents_one_draft ON pad_documents "
        "(consultation_id, document_type) "
        "WHERE status = 'draft' AND consultation_id IS NOT NULL"
    )

    op.create_table(
        "pad_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_type", sa.String(48), nullable=False),
        sa.Column("department", _department(), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("values", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_pad_templates_document_type", "pad_templates", ["document_type"])
    op.create_index("ix_pad_templates_owner_id", "pad_templates", ["owner_id"])

    op.create_table(
        "pad_catalogue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("department", sa.String(32), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized", sa.String(255), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("category", "department", "normalized",
                            name="uq_pad_catalogue_phrase"),
    )
    op.create_index("ix_pad_catalogue_lookup", "pad_catalogue",
                    ["category", "department", "use_count"])


def downgrade() -> None:
    op.drop_table("pad_catalogue")
    op.drop_table("pad_templates")
    op.execute("DROP INDEX IF EXISTS uq_pad_documents_one_draft")
    op.drop_table("pad_documents")
    op.execute("DROP INDEX IF EXISTS uq_pad_layouts_scope")
    op.drop_table("pad_layouts")
    _STATUS.drop(op.get_bind(), checkfirst=True)
