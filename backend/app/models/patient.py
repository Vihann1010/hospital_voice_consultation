from datetime import date
from typing import List, Optional

from sqlalchemy import Date, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Gender


class Patient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "patients"

    # The patient's permanent hospital number, spoken at the counter and
    # written on their paper file. Nullable only so that records migrated
    # from the previous system can be imported before numbers are assigned;
    # everything created here always has one.
    uhid: Mapped[Optional[str]] = mapped_column(String(16), unique=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[Gender] = mapped_column(
        Enum(Gender, name="gender", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(20), index=True, nullable=False)

    # Age is captured at registration because patients report it directly;
    # date of birth is recorded when known and is what should be trusted.
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    address: Mapped[Optional[str]] = mapped_column(String(512))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    blood_group: Mapped[Optional[str]] = mapped_column(String(8))
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(255))
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    # Identifier from the system this record was migrated from, so a re-run
    # of the import updates rather than duplicates.
    legacy_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    consultations: Mapped[List["Consultation"]] = relationship(  # noqa: F821
        back_populates="patient", cascade="all, delete-orphan"
    )
