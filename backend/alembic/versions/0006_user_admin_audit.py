"""Audit actions for staff account administration.

Creating an account and changing what someone is allowed to do are the entries
that explain every other entry in the audit trail, so they need their own
actions rather than being recorded as something adjacent.

Postgres allows ADD VALUE inside a transaction from version 12 provided the
new value is not used in the same transaction; this migration only declares
them, so it is safe under Alembic's transactional DDL.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_user_admin_audit"
down_revision: Union[str, None] = "0005_staff_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ACTIONS = ("user_create", "user_update")


def upgrade() -> None:
    for action in NEW_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")


def downgrade() -> None:
    # Postgres cannot remove a value from an enum type, and rebuilding it here
    # would mean deleting the audit rows that use it. An audit trail is not
    # something a schema rollback may quietly destroy, so this is a no-op and
    # the two values remain declared but unused.
    pass
