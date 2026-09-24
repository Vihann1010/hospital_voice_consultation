"""Join the two lines of work: the prescribing pad, and this clinic.

Both branched from 0030. The hospital's side added what a signed pad issues
(0031_pad_issues_prescription); this clinic's side added gastroenterology,
dentistry and the practices (0031_gastroenterology_department onward). Neither
touches the other's tables, so they merge rather than rebase: each keeps its
own revision id, and a database that has already applied one of them upgrades
through the other and stops here.
"""
from typing import Sequence, Union

revision: str = "0037_merge_pad_and_practices"
down_revision: Union[str, Sequence[str], None] = (
    "0036_patient_practice",
    "0031_pad_issues_prescription",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Nothing to do: the two chains are independent."""


def downgrade() -> None:
    """Nothing to undo."""
