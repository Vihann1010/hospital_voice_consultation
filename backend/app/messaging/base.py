"""Provider-agnostic outbound messaging.

Every delivery path in the platform goes through `MessagingProvider`, so
replacing WhatsApp Cloud with Twilio, Gupshup or an on-premise gateway is a
configuration change. Providers return a `SendResult` rather than raising for
delivery problems: the difference between "retry this" and "give up" is a
property of the result, and the retry policy lives in one place instead of
being reimplemented per vendor.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class OutboundDocument:
    filename: str
    content: bytes
    content_type: str = "application/pdf"
    caption: Optional[str] = None
    # Some providers (Twilio) fetch the file over HTTP instead of accepting bytes.
    public_url: Optional[str] = None


@dataclass
class SendResult:
    ok: bool
    provider: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    # True when the same call might succeed later (network, rate limit, 5xx).
    retryable: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


class MessagingProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def send_document(
        self, *, to: str, document: OutboundDocument
    ) -> SendResult:
        """Deliver a document to a phone number in E.164 form."""

    async def send_text(self, *, to: str, body: str) -> SendResult:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


def normalize_phone(raw: str, default_country_code: str = "91") -> Optional[str]:
    """Return digits only in E.164 form without '+', or None if implausible.

    Indian numbers are stored locally in many shapes ("98390 12345",
    "+91-98390-12345", "098390 12345"); WhatsApp wants "919839012345".
    """
    if not raw:
        return None
    digits = "".join(character for character in str(raw) if character.isdigit())
    if not digits:
        return None
    # Drop a leading trunk zero before applying the country code.
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = f"{default_country_code}{digits}"
    elif digits.startswith("00"):
        digits = digits[2:]
    if not 10 <= len(digits) <= 15:
        return None
    return digits
