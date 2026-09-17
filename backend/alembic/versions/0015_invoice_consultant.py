"""Attribute every bill to a consultant directly.

Found while testing the pricing rules: a bill can be raised at the counter
with no visit attached, and the consultant was only reachable through the
visit. So the free-follow-up and first-consultation rules fired for patients
whose bills happened to have a visit and silently did nothing for the rest —
the worst kind of pricing bug, because it is invisible until a patient
notices they were charged for something a colleague got free.

Part 5 needs the same attribution for consultant-wise billing and the payout
report, so this is where it belongs rather than bolted on later.

Existing rows are backfilled from their visit where they have one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_invoice_consultant"
down_revision: Union[str, None] = "0014_pricing_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("consultant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultants.id", ondelete="SET NULL")),
    )
    op.add_column(
        "invoices",
        sa.Column("doctor_name", sa.String(255), nullable=False, server_default=""),
    )
    op.create_index("ix_invoices_consultant_id", "invoices", ["consultant_id"])

    # Backfill from the visit, which is where this lived until now.
    op.execute(
        """
        UPDATE invoices AS i
           SET doctor_name = v.doctor_name
        FROM visits AS v
        WHERE i.visit_id = v.id AND v.doctor_name <> ''
        """
    )
    # And match those names to the register where they line up, so the
    # payout report has ids rather than strings for historical bills too.
    op.execute(
        """
        UPDATE invoices AS i
           SET consultant_id = c.id
        FROM consultants AS c
        WHERE i.consultant_id IS NULL AND i.doctor_name = c.full_name
        """
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_consultant_id", table_name="invoices")
    op.drop_column("invoices", "doctor_name")
    op.drop_column("invoices", "consultant_id")
