"""Per-document print settings.

Margins, fonts and letterhead move when the stationery changes, which should
not require a deployment. Seeded with the values the two existing renderers
already hardcode, so every document prints byte-for-byte as it does today
until somebody deliberately changes it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_print_settings"
down_revision: Union[str, None] = "0008_patient_master"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# document_type, watermark_duplicates.
# A duplicate bill must be stamped or an auditor cannot tell it from the
# original; a reprinted prescription should not be, because the patient is
# simply carrying it to a pharmacy.
SEED = [
    ("invoice", True),
    ("receipt", True),
    ("prescription", False),
    ("lab_report", False),
    ("discharge_summary", False),
]


def upgrade() -> None:
    op.create_table(
        "print_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_type", sa.String(48), nullable=False, unique=True),
        sa.Column("margin_top", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("margin_bottom", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("margin_left", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("margin_right", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("font_family", sa.String(64), nullable=False, server_default="Helvetica"),
        sa.Column("font_size", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("header_image", sa.String(255)),
        sa.Column("header_height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("footer_image", sa.String(255)),
        sa.Column("footer_height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("footer_remark", sa.Text()),
        sa.Column("watermark_duplicates", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_print_settings_document_type", "print_settings", ["document_type"])

    for document_type, watermark in SEED:
        op.execute(
            sa.text(
                "INSERT INTO print_settings (id, document_type, watermark_duplicates,"
                " created_at, updated_at)"
                " VALUES (gen_random_uuid(), :dt, :wm, now(), now())"
            ).bindparams(dt=document_type, wm=watermark)
        )


def downgrade() -> None:
    op.drop_table("print_settings")
