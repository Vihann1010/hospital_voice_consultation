"""A day case belongs to a visit, not an admission.

The theatre was written for an inpatient: a case is booked against an
admission, and the charge for it is posted to that admission's running bill.
A clinic that scopes a patient and sends them home the same hour has no
admission to bill, so every case ended with "bill it at the counter" and a
procedure that nobody had to remember to charge for.

The visit is the OPD equivalent of the admission — it is what the counter
already bills against — so a day case is booked against one, and the charge
goes where the patient's other charges for that day went.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_surgery_visit"
down_revision: Union[str, None] = "0032_gastro_investigation_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("surgeries", sa.Column("visit_id", sa.dialects.postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_surgeries_visit_id", "surgeries", "visits", ["visit_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_surgeries_visit_id", "surgeries", ["visit_id"])


def downgrade() -> None:
    op.drop_index("ix_surgeries_visit_id", table_name="surgeries")
    op.drop_constraint("fk_surgeries_visit_id", "surgeries", type_="foreignkey")
    op.drop_column("surgeries", "visit_id")
