"""Inpatient documents on the Visit Pad, and a nurse role to write them.

The nursing initial assessment and each shift's nursing note are the nurse's
documents, written and signed by the nurse. Until now there was no nurse role:
ward charting was guarded only by the permission to read a patient, which any
logged-in member of staff holds.

The enum value is added and never removed on downgrade — PostgreSQL cannot drop
an enum value, and user rows may already carry it.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019_inpatient_record"
down_revision: Union[str, None] = "0018_visit_pad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'nurse'")
    # The case sheet lists an admission's documents by type, newest first,
    # every time a tab is opened.
    op.create_index(
        "ix_pad_documents_admission_type",
        "pad_documents",
        ["admission_id", "document_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pad_documents_admission_type", table_name="pad_documents")
