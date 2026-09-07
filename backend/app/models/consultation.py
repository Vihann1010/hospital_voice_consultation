import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConsultationStatus, Department, TurnRole
from app.models.patient import Patient


class Consultation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "consultations"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    department: Mapped[Department] = mapped_column(
        Enum(Department, name="department", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[ConsultationStatus] = mapped_column(
        Enum(
            ConsultationStatus,
            name="consultation_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ConsultationStatus.IN_PROGRESS,
        index=True,
    )
    medical_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    patient: Mapped[Patient] = relationship(back_populates="consultations")
    turns: Mapped[List["ConversationTurn"]] = relationship(
        back_populates="consultation",
        cascade="all, delete-orphan",
        order_by="ConversationTurn.sequence",
    )


class ConversationTurn(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversation_turns"

    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[TurnRole] = mapped_column(
        Enum(TurnRole, name="turn_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    interrupted: Mapped[bool] = mapped_column(default=False, nullable=False)

    consultation: Mapped[Consultation] = relationship(back_populates="turns")
