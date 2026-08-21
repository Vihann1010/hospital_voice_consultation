"""Immutable audit trail.

Patient records are sensitive, so every access and every clinical action is
recorded with who, what, when and from where. Rows are written once and never
updated — there is deliberately no update path in the repository.

Writes are best-effort and must never fail a clinical request: if the audit
insert errors, the action still completes and the failure is logged. Losing an
audit row is bad; blocking a doctor mid-consultation is worse.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, func

_VALUES = lambda e: [m.value for m in e]  # noqa: E731  (see models/investigation.py)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AuditAction


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_actor_time", "actor_id", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_action_time", "action", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action", values_callable=_VALUES), nullable=False
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    actor_role: Mapped[Optional[str]] = mapped_column(String(32))

    entity_type: Mapped[Optional[str]] = mapped_column(String(48))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)

    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    request_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    success: Mapped[bool] = mapped_column(nullable=False, default=True)
    detail: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
