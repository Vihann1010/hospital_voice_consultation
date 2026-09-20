"""Investigation categories for a gastroenterology clinic.

GI work does not fit the existing categories. H. pylori testing, stool
studies and liver elastography are not blood, urine or ultrasound; and a
gastroscopy is booked, consented and reported like a procedure rather than
collected like a sample, so it gets its own category rather than being filed
under a scan it is not.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0032_gastro_investigation_categories"
down_revision: Union[str, None] = "0031_gastroenterology_department"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for value in ("gastroenterology", "endoscopy"):
        op.execute(f"ALTER TYPE investigation_category ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres cannot drop an enum value without rewriting the type and every
    # column using it, and orders may already reference these. Left in place.
    pass
