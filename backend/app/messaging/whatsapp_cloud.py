"""Meta WhatsApp Cloud API provider.

Two-step delivery: upload the PDF to /media to obtain a media id, then send a
document message referencing it. This avoids needing a publicly reachable URL
for the file, which matters for a hospital deployment behind a firewall.
"""
from typing import Any, Dict

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.messaging.base import MessagingProvider, OutboundDocument, SendResult

logger = get_logger(__name__)

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class WhatsAppCloudProvider(MessagingProvider):
    name = "whatsapp_cloud"

    def __init__(self) -> None:
        self.base_url = settings.WHATSAPP_API_BASE.rstrip("/")
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.token = settings.WHATSAPP_ACCESS_TOKEN
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.MESSAGING_TIMEOUT_S, connect=10.0),
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def _configured(self) -> bool:
        return bool(self.phone_number_id and self.token)

    async def _upload(self, document: OutboundDocument) -> Dict[str, Any]:
        files = {
            "file": (document.filename, document.content, document.content_type),
            "messaging_product": (None, "whatsapp"),
            "type": (None, document.content_type),
        }
        response = await self._client.post(
            f"{self.base_url}/{self.phone_number_id}/media", files=files
        )
        response.raise_for_status()
        return response.json()

    async def send_document(self, *, to: str, document: OutboundDocument) -> SendResult:
        if not self._configured():
            return SendResult(
                ok=False, provider=self.name, retryable=False,
                error="WhatsApp is not configured (WHATSAPP_PHONE_NUMBER_ID / "
                      "WHATSAPP_ACCESS_TOKEN are unset).",
            )
        try:
            uploaded = await self._upload(document)
            media_id = uploaded.get("id")
            if not media_id:
                return SendResult(ok=False, provider=self.name, retryable=True,
                                  error=f"Media upload returned no id: {uploaded}",
                                  raw=uploaded)

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "document",
                "document": {"id": media_id, "filename": document.filename},
            }
            if document.caption:
                payload["document"]["caption"] = document.caption[:1024]

            response = await self._client.post(
                f"{self.base_url}/{self.phone_number_id}/messages", json=payload
            )
            response.raise_for_status()
            body = response.json()
            message_id = (body.get("messages") or [{}])[0].get("id")
            return SendResult(ok=True, provider=self.name, provider_message_id=message_id,
                              raw=body)

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = exc.response.text[:400]
            # 131047 = re-engagement required (outside the 24h window); a retry
            # of the same free-form message will not help.
            retryable = status in _RETRYABLE_STATUS
            logger.warning("whatsapp_send_failed",
                           extra={"status": status, "detail": detail})
            return SendResult(ok=False, provider=self.name, retryable=retryable,
                              error=f"HTTP {status}: {detail}")
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return SendResult(ok=False, provider=self.name, retryable=True,
                              error=f"Network error: {exc!r}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("whatsapp_send_error")
            return SendResult(ok=False, provider=self.name, retryable=False,
                              error=repr(exc))

    async def send_text(self, *, to: str, body: str) -> SendResult:
        if not self._configured():
            return SendResult(ok=False, provider=self.name, retryable=False,
                              error="WhatsApp is not configured.")
        try:
            response = await self._client.post(
                f"{self.base_url}/{self.phone_number_id}/messages",
                json={"messaging_product": "whatsapp", "to": to, "type": "text",
                      "text": {"body": body[:4096]}},
            )
            response.raise_for_status()
            payload = response.json()
            return SendResult(ok=True, provider=self.name,
                              provider_message_id=(payload.get("messages") or [{}])[0].get("id"),
                              raw=payload)
        except httpx.HTTPStatusError as exc:
            return SendResult(ok=False, provider=self.name,
                              retryable=exc.response.status_code in _RETRYABLE_STATUS,
                              error=f"HTTP {exc.response.status_code}: {exc.response.text[:300]}")
        except Exception as exc:  # noqa: BLE001
            return SendResult(ok=False, provider=self.name, retryable=True, error=repr(exc))

    async def aclose(self) -> None:
        await self._client.aclose()
