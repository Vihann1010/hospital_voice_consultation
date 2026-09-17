"""Let an appointment be booked for somebody who is not a patient yet.

Answering the telephone should not require creating a patient record. The
previous shape forced it: `patient_id` was mandatory, so a clerk taking a
booking from a stranger had to register them first — issuing a UHID to
somebody who may never arrive, and creating a second record for the same
person the next time they rang.

`patient_id` becomes nullable, and the caller's own words are stored beside
it. The check constraint is what keeps this honest: a booking must name
somebody, either by record or by name and number.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_appointment_callers"
down_revision: Union[str, None] = "0010_appointments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("appointments", "patient_id", nullable=True)

    op.add_column("appointments", sa.Column("caller_name", sa.String(255)))
    op.add_column("appointments", sa.Column("caller_phone", sa.String(20)))
    op.add_column("appointments", sa.Column("caller_age", sa.Integer()))
    op.add_column(
        "appointments",
        sa.Column("caller_gender", postgresql.ENUM(name="gender", create_type=False)),
    )
    # Reception's first question to a caller is their phone number, and the
    # answer decides whether this is a new person or one already on file.
    op.create_index("ix_appointments_caller_phone", "appointments", ["caller_phone"])

    op.create_check_constraint(
        "ck_appointment_has_someone",
        "appointments",
        "patient_id IS NOT NULL OR (caller_name IS NOT NULL AND caller_phone IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointment_has_someone", "appointments", type_="check")
    op.drop_index("ix_appointments_caller_phone", table_name="appointments")
    op.drop_column("appointments", "caller_gender")
    op.drop_column("appointments", "caller_age")
    op.drop_column("appointments", "caller_phone")
    op.drop_column("appointments", "caller_name")
    # Bookings taken from unregistered callers cannot survive this: the column
    # they depend on is about to become mandatory again. They are deleted
    # rather than silently attached to some arbitrary patient.
    op.execute("DELETE FROM appointments WHERE patient_id IS NULL")
    op.alter_column("appointments", "patient_id", nullable=False)
