"""Twilio WhatsApp provider.

Twilio fetches media over HTTP rather than accepting bytes, so the document
must expose a publicly reachable URL. The prescription service supplies a
signed, expiring link for exactly this purpose.
"""
import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.messaging.base import MessagingProvider, OutboundDocument, SendResult

logger = get_logger(__name__)

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class TwilioWhatsAppProvider(MessagingProvider):
    name = "twilio_whatsapp"

    def __init__(self) -> None:
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_WHATSAPP_FROM
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.MESSAGING_TIMEOUT_S, connect=10.0),
            auth=(self.account_sid, self.auth_token),
        )

    def _configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)

    async def send_document(self, *, to: str, document: OutboundDocument) -> SendResult:
        if not self._configured():
            return SendResult(ok=False, provider=self.name, retryable=False,
                              error="Twilio is not configured.")
        if not document.public_url:
            return SendResult(
                ok=False, provider=self.name, retryable=False,
                error="Twilio requires a publicly reachable media URL. Set "
                      "PUBLIC_BASE_URL so signed document links can be generated.",
            )
        try:
            response = await self._client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json",
                data={
                    "From": f"whatsapp:+{self.from_number.lstrip('+')}",
                    "To": f"whatsapp:+{to.lstrip('+')}",
                    "Body": document.caption or "Your prescription from Satya Hospital",
                    "MediaUrl": document.public_url,
                },
            )
            response.raise_for_status()
            body = response.json()
            return SendResult(ok=True, provider=self.name,
                              provider_message_id=body.get("sid"), raw=body)
        except httpx.HTTPStatusError as exc:
            return SendResult(ok=False, provider=self.name,
                              retryable=exc.response.status_code in _RETRYABLE_STATUS,
                              error=f"HTTP {exc.response.status_code}: {exc.response.text[:300]}")
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return SendResult(ok=False, provider=self.name, retryable=True,
                              error=f"Network error: {exc!r}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("twilio_send_error")
            return SendResult(ok=False, provider=self.name, retryable=False, error=repr(exc))

    async def aclose(self) -> None:
        await self._client.aclose()
