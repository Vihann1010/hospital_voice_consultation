"""Certificates and consent forms: serial numbers and the signed paper copy.

Both are pad documents, so no new table. A serial number is given when a
certificate or consent form is first signed and kept by its corrections; the
paper columns record that the patient's signed copy of a consent form came
back, and who received it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_certificates_consent"
down_revision: Union[str, None] = "0020_theatre"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'consent_paper_signed'")
    op.add_column("pad_documents", sa.Column("serial_number", sa.String(24), nullable=True))
    op.add_column("pad_documents", sa.Column("paper_signed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pad_documents", sa.Column("paper_signed_by_name", sa.String(255), nullable=True))
    op.create_index("ix_pad_documents_serial_number", "pad_documents", ["serial_number"])


def downgrade() -> None:
    op.drop_index("ix_pad_documents_serial_number", table_name="pad_documents")
    op.drop_column("pad_documents", "paper_signed_by_name")
    op.drop_column("pad_documents", "paper_signed_at")
    op.drop_column("pad_documents", "serial_number")
