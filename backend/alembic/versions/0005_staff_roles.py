"""Split the single "staff" role into manager, supervisor and reception.

Three kinds of elevated authority were collapsed into "admin or doctor":
seeing hospital revenue, returning money to a patient, and carrying clinical
responsibility. That is why a doctor could reprice a service. This separates
them, matching the roles the hospital already uses.

Existing "staff" users become "reception", which is the same set of
permissions they held before under the old name.

Conditional on purpose: the baseline migration builds from the ORM metadata,
so a database created after this change already has the five values and there
is nothing to alter. Only a database created before it carries "staff".
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_staff_roles"
down_revision: Union[str, None] = "0004_ipd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = "'admin', 'manager', 'doctor', 'supervisor', 'reception'"


def upgrade() -> None:
    # Postgres cannot drop a value from an enum, so the type is rebuilt and
    # the column recast in one step, remapping the retired value as it goes.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'user_role' AND e.enumlabel = 'staff'
            ) THEN
                CREATE TYPE user_role_new AS ENUM ({ROLES});

                ALTER TABLE users
                    ALTER COLUMN role TYPE user_role_new
                    USING (
                        CASE role::text
                            WHEN 'staff' THEN 'reception'
                            ELSE role::text
                        END
                    )::user_role_new;

                DROP TYPE user_role;
                ALTER TYPE user_role_new RENAME TO user_role;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Lossy: manager, supervisor and reception all collapse back to staff,
    # because the old vocabulary has no way to tell them apart.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'user_role' AND e.enumlabel = 'staff'
            ) THEN
                CREATE TYPE user_role_old AS ENUM ('admin', 'doctor', 'staff');

                ALTER TABLE users
                    ALTER COLUMN role TYPE user_role_old
                    USING (
                        CASE role::text
                            WHEN 'admin' THEN 'admin'
                            WHEN 'doctor' THEN 'doctor'
                            ELSE 'staff'
                        END
                    )::user_role_old;

                DROP TYPE user_role;
                ALTER TYPE user_role_old RENAME TO user_role;
            END IF;
        END $$;
        """
    )
