"""Initial schema — baseline for every table created in phases 1 to 5.

Existing deployments provisioned by the old `create_all` path adopt this
baseline without re-creating anything:

    alembic stamp 0001_initial

Fresh deployments run `alembic upgrade head` and get the same schema.

This still creates every table in the *current* ORM in one shot, not just
a phase 1-5 subset — deliberately. `Base.metadata.create_all()` topologically
sorts by foreign key, and several early tables (insurance_policies, for one)
carry an FK column added by a much later migration (0028) pointing at a
table created by another later migration (organisations, from 0014).
Scoping this migration down to only its "own" tables breaks that ordering:
the FK target does not exist yet. Creating everything at once, as this
always has, is what makes that safe.

The real problem this caused — every migration from `0007` onward using a
plain `op.create_table` for something this step already built, so a fresh
install hits "relation already exists" — is fixed on the other side
instead: those migrations now check the table does not already exist
first, the same defensive pattern `0003` and `0004` already used.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The models are the single source of truth for the baseline: creating from
    # metadata guarantees this migration and the ORM cannot drift apart.
    from app.models.registry import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    from app.models.registry import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
