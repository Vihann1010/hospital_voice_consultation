"""Development provider: records the send instead of transmitting it.

Used when MESSAGING_PROVIDER=console, which is the default so a fresh
deployment never silently attempts to message real patients.
"""
import uuid

from app.core.logging import get_logger
from app.messaging.base import MessagingProvider, OutboundDocument, SendResult

logger = get_logger(__name__)


class ConsoleProvider(MessagingProvider):
    name = "console"

    async def send_document(self, *, to: str, document: OutboundDocument) -> SendResult:
        logger.info(
            "console_message_document",
            extra={"to": to, "filename": document.filename,
                   "bytes": len(document.content), "caption": document.caption},
        )
        return SendResult(ok=True, provider=self.name,
                          provider_message_id=f"console-{uuid.uuid4()}")

    async def send_text(self, *, to: str, body: str) -> SendResult:
        logger.info("console_message_text", extra={"to": to, "body": body[:200]})
        return SendResult(ok=True, provider=self.name,
                          provider_message_id=f"console-{uuid.uuid4()}")
