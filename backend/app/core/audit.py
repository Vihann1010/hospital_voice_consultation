"""Audit trail writer.

Deliberately fire-and-forget from the caller's perspective: `record()` opens its
own session so an audit write can never poison the surrounding transaction, and
swallows its own errors after logging them.
"""
import uuid
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.enums import AuditAction

logger = get_logger(__name__)


async def record(
    action: AuditAction,
    *,
    actor_id: Optional[uuid.UUID] = None,
    actor_name: str = "",
    actor_role: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
    success: bool = True,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                AuditLog(
                    action=action,
                    actor_id=actor_id,
                    actor_name=actor_name[:255],
                    actor_role=actor_role,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    patient_id=patient_id,
                    ip_address=(ip_address or "")[:64] or None,
                    user_agent=(user_agent or "")[:255] or None,
                    request_id=request_id,
                    success=success,
                    detail=detail,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 - auditing must never break the request
        logger.exception("audit_write_failed", extra={"action": action.value})


def client_ip(request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
