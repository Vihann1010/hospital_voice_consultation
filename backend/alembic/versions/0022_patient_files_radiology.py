"""Patient file attachments, and radiology reports written against an order.

Attachments are never deleted: a file uploaded to the wrong patient or in
error is withdrawn with a reason and kept, because a medical record that can
lose pages cannot be relied on.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_patient_files_radiology"
down_revision: Union[str, None] = "0021_certificates_consent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = (
    "identity_proof", "referral_letter", "previous_records", "outside_investigation",
    "signed_consent", "clinical_photograph", "insurance", "other",
)
_CATEGORY = postgresql.ENUM(*CATEGORIES, name="patient_file_category")


def upgrade() -> None:
    for value in ("file_upload", "file_withdraw"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
    _CATEGORY.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "patient_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultations.id", ondelete="SET NULL")),
        sa.Column("admission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("admissions.id", ondelete="SET NULL")),
        sa.Column("pad_document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pad_documents.id", ondelete="SET NULL")),
        sa.Column("category", postgresql.ENUM(name="patient_file_category", create_type=False),
                  nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("document_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("stored_filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("uploaded_by_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_by_name", sa.String(255)),
        sa.Column("withdraw_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_patient_files_patient", "patient_files", ["patient_id", "created_at"])
    op.create_index("ix_patient_files_admission", "patient_files", ["admission_id"])
    op.create_index("ix_patient_files_consultation", "patient_files", ["consultation_id"])
    op.create_index("ix_patient_files_pad_document", "patient_files", ["pad_document_id"])
    op.create_index("ix_patient_files_checksum", "patient_files", ["patient_id", "checksum_sha256"])

    op.add_column("pad_documents", sa.Column(
        "order_item_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("investigation_order_items.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_pad_documents_order_item", "pad_documents", ["order_item_id"])


def downgrade() -> None:
    op.drop_index("ix_pad_documents_order_item", table_name="pad_documents")
    op.drop_column("pad_documents", "order_item_id")
    op.drop_table("patient_files")
    _CATEGORY.drop(op.get_bind(), checkfirst=True)
