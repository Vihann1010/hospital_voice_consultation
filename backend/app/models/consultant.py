"""Consultants: the doctors the hospital bills and schedules for.

**A consultant is not a login.** They are separate on purpose. A visiting
surgeon operates one afternoon a week and never touches the software, and a
receptionist has a login but never appears on a prescription. Tying the two
together would mean inventing dormant accounts for people who do not use the
system, and would make deactivating someone's access delete them from the
history of the patients they treated. The link is optional in both directions.

**Their settings drive three other modules.** Appointment slot length decides
what the scheduler offers; the free-follow-up window decides whether the
counter charges a returning patient; the qualification and registration number
are printed on every prescription they sign. Those rules belong to the person,
not to the screen that happens to read them, which is why they live here rather
than as constants in three different places.
"""
import uuid
from datetime import time
from typing import List, Optional

from sqlalchemy import (
    Boolean, Enum as SAEnum, ForeignKey, Integer, String, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Department, Gender

_VALUES = lambda e: [m.value for m in e]  # noqa: E731


class Consultant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "consultants"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, name="department", values_callable=_VALUES),
        nullable=False,
        index=True,
    )
    sex: Mapped[Optional[Gender]] = mapped_column(
        SAEnum(Gender, name="gender", values_callable=_VALUES)
    )

    # Printed under the signature on every prescription and report they sign.
    # The registration number is what makes a prescription a legal document,
    # so it is captured here rather than typed per prescription.
    qualification: Mapped[Optional[str]] = mapped_column(String(255))
    registration_number: Mapped[Optional[str]] = mapped_column(String(120))

    phone_number: Mapped[Optional[str]] = mapped_column(String(20))

    # The login this consultant uses, when they use one at all. Nullable both
    # ways: visiting consultants have no account, and most accounts are not
    # consultants.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), unique=True, index=True
    )

    # Scheduling: how long one appointment with them takes.
    appointment_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    # When they actually sit in the OPD. The scheduler offers slots inside
    # this window only — a hospital that opens at nine should not be able to
    # book an eight o'clock appointment nobody will be there for. Days are
    # ISO weekday numbers (Monday 1 ... Sunday 7); a consultant who does not
    # sit on Sunday simply has no slots that day rather than a special case.
    opd_start_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(9, 0)
    )
    opd_end_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(17, 0)
    )
    opd_days: Mapped[str] = mapped_column(String(20), nullable=False, default="1,2,3,4,5,6")

    # Some consultants see a new patient once without charge. Kept as their
    # own setting rather than a hospital-wide switch, because it is their fee
    # being waived.
    first_consultation_free: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # A patient returning inside this window is not charged a consultation
    # again. Zero means they always pay. This is the rule the counter applies
    # without being asked, so it has to be the consultant's own number.
    free_follow_up_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Which tariff line is charged for a new consultation with them. Left
    # unset, the counter falls back to the department's standard rate.
    consultation_service_code: Mapped[Optional[str]] = mapped_column(String(32))

    # Their share of what the hospital bills for their services, in whole
    # percent. Read by the payout report; recorded here so a payout run can be
    # reproduced from the settings that applied.
    payout_share_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Which kinds of billed service the share is taken on. Consultations only,
    # unless agreed otherwise; see app/accounts/payout.py.
    payout_categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["consultation"])

    # Which pickers this consultant shows up in. A visiting radiologist who
    # only reads films has no business on the OPD registration screen, but
    # still needs to appear when a diagnostics report is signed.
    display_in_opd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_in_ipd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_in_diagnostics: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # Lower sorts first within a department; ties break on name. Zero for
    # everyone by default, so a hospital that never touches this gets the
    # alphabetical order it already had.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The department's usual doctor — floats to the top of its picker and is
    # the default selection, ahead of sort_order.
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    rates: Mapped[List["ConsultantRate"]] = relationship(
        back_populates="consultant", cascade="all, delete-orphan"
    )


class ConsultantRate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """What one consultant charges for one service, instead of the tariff.

    Mirrors NegotiatedRate: a senior consultant's own procedure rate differs
    from the hospital's standard one, and averaging that into a single number
    loses the agreement the same way a blanket discount would.
    """

    __tablename__ = "consultant_rates"
    __table_args__ = (
        UniqueConstraint(
            "consultant_id", "service_item_id", name="uq_rate_consultant_service"
        ),
    )

    consultant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    service_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    rate_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    consultant: Mapped["Consultant"] = relationship(back_populates="rates")


class ReferralProvider(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Outside doctors and clinics who send patients here.

    Kept apart from Consultant because the hospital pays one and thanks the
    other: a referral provider never appears on a prescription and is never
    scheduled, but referral volume is what the practice is measured on.
    """

    __tablename__ = "referral_providers"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    clinic_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone_number: Mapped[Optional[str]] = mapped_column(String(20))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
