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
    # The practice this patient is registered with (its three letters). A
    # person seen by two practices under one roof is two patients, one in each.
    # Empty on a record from before practices existed: the site's default.
    practice: Mapped[Optional[str]] = mapped_column(String(3), index=True)

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

    # ------------------------------------------------------------ identity
    title: Mapped[Optional[str]] = mapped_column(String(16))
    # Most patients here are identified in relation to a family member, and
    # the relation is what produces the S/o, D/o, W/o prefix on every printed
    # document — so it is stored as a relation, not baked into a name string.
    guardian_relation: Mapped[Optional[str]] = mapped_column(String(16))
    guardian_name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))

    # Government identification. The type is stored beside the value because
    # what counts as valid proof differs by scheme, and a bare number cannot
    # be checked. Never store a full Aadhaar number here — record the last
    # four digits, or use another accepted document.
    govt_id_type: Mapped[Optional[str]] = mapped_column(String(32))
    govt_id_number: Mapped[Optional[str]] = mapped_column(String(64))

    # ------------------------------------------------------------- address
    state: Mapped[Optional[str]] = mapped_column(String(120))
    country: Mapped[Optional[str]] = mapped_column(String(120))
    pincode: Mapped[Optional[str]] = mapped_column(String(12))

    # -------------------------------------------------------- demographics
    religion: Mapped[Optional[str]] = mapped_column(String(64))
    marital_status: Mapped[Optional[str]] = mapped_column(String(32))
    nationality: Mapped[Optional[str]] = mapped_column(String(64))
    occupation: Mapped[Optional[str]] = mapped_column(String(120))

    # Free classification the hospital defines for itself — camp patients,
    # staff dependants, panel patients. Kept as plain labels rather than
    # enums because the categories change without a deployment.
    category: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    group_one: Mapped[Optional[str]] = mapped_column(String(64))
    group_two: Mapped[Optional[str]] = mapped_column(String(64))
    # Identifier from the system this record was migrated from, so a re-run
    # of the import updates rather than duplicates.
    legacy_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    consultations: Mapped[List["Consultation"]] = relationship(  # noqa: F821
        back_populates="patient", cascade="all, delete-orphan"
    )


class PatientFieldSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Which registration fields this hospital asks for, and which it insists on.

    The old system let each hospital decide this, and the reason matters: a
    maternity patient's guardian relation is essential and their occupation is
    noise, while a trauma admission is the reverse. Hardcoding the form means
    the counter either types dashes into fields it does not need or loses data
    it does.

    One row per field. A field with no row falls back to optional and visible,
    so adding a column to Patient never silently hides it.
    """

    __tablename__ = "patient_field_settings"

    # Matches the attribute name on Patient, e.g. "occupation".
    field_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # required | optional | hidden
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="optional")
    # Overrides the default wording on the form, for hospitals that call a
    # field something else.
    label: Mapped[Optional[str]] = mapped_column(String(120))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
