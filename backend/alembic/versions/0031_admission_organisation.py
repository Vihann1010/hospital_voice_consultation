"""Payer on an IPD admission.

OPD registration has had a "Paid by" organisation since 0014; admission had
no equivalent, so an insured inpatient's policy was invisible until someone
thought to say so out loud at discharge.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_admission_organisation"
down_revision: Union[str, None] = "0030_invoice_line_remark"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "admissions",
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="SET NULL")),
    )
    op.create_index("ix_admissions_organisation_id", "admissions", ["organisation_id"])


def downgrade() -> None:
    op.drop_index("ix_admissions_organisation_id", table_name="admissions")
    op.drop_column("admissions", "organisation_id")
