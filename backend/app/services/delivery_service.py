"""Outbound delivery: send, track, retry.

The retry policy lives here rather than in any provider, so swapping vendors
never changes how failures are handled. A delivery row is the durable record of
intent: it survives restarts, accumulates an attempt history, and is picked up
by a background sweeper when `next_retry_at` falls due.

Failures are split into retryable (network, rate limit, 5xx) and terminal
(unconfigured provider, invalid number, outside the messaging window). Only the
first kind is rescheduled — retrying a terminal failure five times just delays
the moment a human notices.
"""
import asyncio
import contextlib
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.messaging.base import OutboundDocument, SendResult, normalize_phone
from app.messaging.factory import get_provider
from app.models.enums import DeliveryChannel, DeliveryStatus
from app.models.prescription import MessageDelivery

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff(attempt: int) -> timedelta:
    """Exponential backoff with jitter, capped."""
    base = settings.MESSAGING_RETRY_BASE_S * (2 ** max(0, attempt - 1))
    capped = min(base, settings.MESSAGING_RETRY_MAX_S)
    return timedelta(seconds=capped * (0.6 + random.random() * 0.5))


class DeliveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------ queueing
    async def queue(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        prescription_id: Optional[uuid.UUID],
        recipient_raw: str,
        requested_by_name: str,
        channel: DeliveryChannel = DeliveryChannel.WHATSAPP,
    ) -> MessageDelivery:
        recipient = normalize_phone(recipient_raw, settings.DEFAULT_COUNTRY_CODE)
        delivery = MessageDelivery(
            entity_type=entity_type,
            entity_id=entity_id,
            prescription_id=prescription_id,
            channel=channel,
            provider=get_provider().name,
            recipient=recipient or (recipient_raw or "")[:32],
            status=DeliveryStatus.PENDING,
            requested_by_name=requested_by_name,
            history=[],
        )
        if recipient is None:
            delivery.status = DeliveryStatus.FAILED
            delivery.is_final = True
            delivery.error_detail = (
                f"'{recipient_raw}' is not a usable phone number. "
                "Correct the patient's number and try again."
            )
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    # -------------------------------------------------------------- sending
    async def attempt(
        self, delivery: MessageDelivery, document: OutboundDocument
    ) -> MessageDelivery:
        """One send attempt, recording the outcome and scheduling any retry."""
        if delivery.is_final:
            return delivery

        provider = get_provider()
        delivery.provider = provider.name
        delivery.status = DeliveryStatus.SENDING
        delivery.attempts += 1
        delivery.last_attempt_at = _now()
        await self.session.flush()

        result: SendResult = await provider.send_document(
            to=delivery.recipient, document=document
        )

        entry: Dict[str, Any] = {
            "at": _now().isoformat(),
            "attempt": delivery.attempts,
            "provider": result.provider,
            "ok": result.ok,
        }

        if result.ok:
            delivery.status = DeliveryStatus.SENT
            delivery.provider_message_id = result.provider_message_id
            delivery.error_detail = None
            delivery.next_retry_at = None
            # Terminal only once the provider confirms delivery via webhook;
            # for providers without callbacks, "sent" is as far as we can know.
            delivery.is_final = provider.name == "console"
            entry["message_id"] = result.provider_message_id
        else:
            delivery.error_detail = (result.error or "Unknown error")[:2000]
            entry["error"] = delivery.error_detail[:300]
            exhausted = delivery.attempts >= settings.MESSAGING_MAX_ATTEMPTS
            if result.retryable and not exhausted:
                delivery.status = DeliveryStatus.PENDING
                delivery.next_retry_at = _now() + _backoff(delivery.attempts)
                entry["next_retry_at"] = delivery.next_retry_at.isoformat()
            else:
                delivery.status = DeliveryStatus.FAILED
                delivery.is_final = True
                delivery.next_retry_at = None
                entry["terminal"] = True
                entry["reason"] = "attempts exhausted" if exhausted else "not retryable"

        delivery.history = list(delivery.history or []) + [entry]
        await self.session.flush()
        logger.info(
            "delivery_attempt",
            extra={
                "delivery_id": str(delivery.id),
                "status": delivery.status.value,
                "attempt": delivery.attempts,
                "provider": delivery.provider,
                "ok": result.ok,
            },
        )
        return delivery

    # ------------------------------------------------------------- webhooks
    async def apply_status_callback(
        self, *, provider_message_id: str, status: str, error: Optional[str] = None
    ) -> Optional[MessageDelivery]:
        """Update a delivery from a provider webhook (delivered / read / failed)."""
        result = await self.session.execute(
            select(MessageDelivery).where(
                MessageDelivery.provider_message_id == provider_message_id
            )
        )
        delivery = result.scalar_one_or_none()
        if delivery is None:
            return None

        mapping = {
            "sent": DeliveryStatus.SENT,
            "delivered": DeliveryStatus.DELIVERED,
            "read": DeliveryStatus.READ,
            "failed": DeliveryStatus.FAILED,
            "undelivered": DeliveryStatus.FAILED,
        }
        new_status = mapping.get(status.lower())
        if new_status is None:
            return delivery

        # Never move a delivery backwards (a late "sent" after "read").
        precedence = {
            DeliveryStatus.PENDING: 0, DeliveryStatus.SENDING: 1, DeliveryStatus.SENT: 2,
            DeliveryStatus.DELIVERED: 3, DeliveryStatus.READ: 4, DeliveryStatus.FAILED: 5,
        }
        if precedence.get(new_status, 0) >= precedence.get(delivery.status, 0):
            delivery.status = new_status

        if new_status in (DeliveryStatus.DELIVERED, DeliveryStatus.READ):
            delivery.delivered_at = delivery.delivered_at or _now()
            delivery.is_final = True
            delivery.next_retry_at = None
        if new_status is DeliveryStatus.FAILED:
            delivery.error_detail = error or delivery.error_detail
            delivery.is_final = True

        delivery.history = list(delivery.history or []) + [
            {"at": _now().isoformat(), "callback": status, "error": error}
        ]
        await self.session.flush()
        await self.session.commit()
        return delivery

    # ------------------------------------------------------------- querying
    async def for_prescription(self, prescription_id: uuid.UUID) -> List[MessageDelivery]:
        result = await self.session.execute(
            select(MessageDelivery)
            .where(MessageDelivery.prescription_id == prescription_id)
            .order_by(MessageDelivery.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, delivery_id: uuid.UUID) -> Optional[MessageDelivery]:
        result = await self.session.execute(
            select(MessageDelivery).where(MessageDelivery.id == delivery_id)
        )
        return result.scalar_one_or_none()

    async def due_for_retry(self, limit: int = 20) -> List[MessageDelivery]:
        result = await self.session.execute(
            select(MessageDelivery)
            .where(
                MessageDelivery.status == DeliveryStatus.PENDING,
                MessageDelivery.is_final.is_(False),
                MessageDelivery.next_retry_at.isnot(None),
                MessageDelivery.next_retry_at <= _now(),
            )
            .order_by(MessageDelivery.next_retry_at)
            .limit(limit)
        )
        return list(result.scalars().all())


class DeliveryRetryWorker:
    """Background sweeper that re-attempts due deliveries.

    Runs in-process on the API node. For a multi-node deployment this is the
    piece to move behind a shared queue; the delivery table already carries all
    the state such a worker would need.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("delivery_retry_worker_started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        # Imported here to avoid a circular import at module load.
        from app.services.prescription_service import PrescriptionService

        while True:
            try:
                await asyncio.sleep(settings.MESSAGING_SWEEP_INTERVAL_S)
                async with AsyncSessionLocal() as session:
                    service = DeliveryService(session)
                    due = await service.due_for_retry()
                    if not due:
                        continue
                    prescriptions = PrescriptionService(session)
                    for delivery in due:
                        document = await prescriptions.build_outbound_document(
                            delivery.entity_id
                        )
                        if document is None:
                            delivery.status = DeliveryStatus.FAILED
                            delivery.is_final = True
                            delivery.error_detail = "The document is no longer available."
                            continue
                        await service.attempt(delivery, document)
                    await session.commit()
                    logger.info("delivery_retry_sweep", extra={"count": len(due)})
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the sweeper must never die
                logger.exception("delivery_retry_sweep_failed")


retry_worker = DeliveryRetryWorker()
