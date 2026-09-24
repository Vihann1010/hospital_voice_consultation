"""What a signed pad issued.

Medicines and advised tests are written on the Visit Pad itself now, and
signing it issues the prescription and places the orders. The document records
what it issued so the link is traceable both ways, and so a pad that is signed
twice — which cannot happen, but is worth being certain of — could never issue
two prescriptions.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_pad_issues_prescription"
down_revision: Union[str, None] = "0030_invoice_line_remark"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pad_documents",
        sa.Column("prescription_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "pad_documents",
        sa.Column(
            "investigation_order_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.create_foreign_key(
        "fk_pad_documents_prescription", "pad_documents", "prescriptions",
        ["prescription_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_pad_documents_investigation_order", "pad_documents", "investigation_orders",
        ["investigation_order_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_pad_documents_investigation_order", "pad_documents",
                       type_="foreignkey")
    op.drop_constraint("fk_pad_documents_prescription", "pad_documents", type_="foreignkey")
    op.drop_column("pad_documents", "investigation_order_id")
    op.drop_column("pad_documents", "prescription_id")
