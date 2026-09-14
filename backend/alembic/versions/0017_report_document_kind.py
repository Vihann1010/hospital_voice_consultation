"""What kind of document each uploaded report is.

Everything a patient photographs used to go through the laboratory parser,
because that was the only parser there was. A prescription read that way turns
its dose notation into measurements: "PAN 40 MG 1-0-0" became an analyte named
PAN, value 40, reference range 1.0 to 0.0, flagged HIGH. A doctor cannot use a
screen that does that, and one invented red flag discredits the real ones
printed beside it.

The column is nullable on purpose. NULL means nobody declared a kind — every
report uploaded before this migration — and that is deliberately distinct from
OTHER. An undeclared document is classified from its own text and, when the
classification is not confident, is shown as unclear rather than analysed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_report_document_kind"
down_revision: Union[str, None] = "0016_report_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND = postgresql.ENUM(
    "prescription", "lab_report", "imaging", "other",
    name="document_kind",
)


def upgrade() -> None:
    # create_type=False on the column: the type is created once, here, rather
    # than implicitly by the first column that mentions it.
    _KIND.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "investigation_reports",
        sa.Column(
            "document_kind",
            postgresql.ENUM(
                "prescription", "lab_report", "imaging", "other",
                name="document_kind", create_type=False,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_investigation_reports_document_kind",
        "investigation_reports",
        ["document_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_investigation_reports_document_kind",
                  table_name="investigation_reports")
    op.drop_column("investigation_reports", "document_kind")
    _KIND.drop(op.get_bind(), checkfirst=True)
