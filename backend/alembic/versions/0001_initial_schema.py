"""Initial schema — baseline for every table created in phases 1 to 5.

Existing deployments provisioned by the old `create_all` path adopt this
baseline without re-creating anything:

    alembic stamp 0001_initial

Fresh deployments run `alembic upgrade head` and get the same schema.
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
