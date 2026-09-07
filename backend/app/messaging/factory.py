"""Provider selection and lifecycle."""
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.messaging.base import MessagingProvider
from app.messaging.console import ConsoleProvider
from app.messaging.twilio_whatsapp import TwilioWhatsAppProvider
from app.messaging.whatsapp_cloud import WhatsAppCloudProvider

logger = get_logger(__name__)

_PROVIDERS = {
    "console": ConsoleProvider,
    "whatsapp_cloud": WhatsAppCloudProvider,
    "twilio": TwilioWhatsAppProvider,
    "twilio_whatsapp": TwilioWhatsAppProvider,
}

_provider: Optional[MessagingProvider] = None


def build_provider() -> MessagingProvider:
    key = (settings.MESSAGING_PROVIDER or "console").lower().strip()
    factory = _PROVIDERS.get(key)
    if factory is None:
        raise ValueError(
            f"Unknown MESSAGING_PROVIDER '{settings.MESSAGING_PROVIDER}'. "
            f"Use one of: {', '.join(sorted(_PROVIDERS))}."
        )
    provider = factory()
    logger.info("messaging_provider_ready", extra={"provider": provider.name})
    return provider


def get_provider() -> MessagingProvider:
    global _provider
    if _provider is None:
        _provider = build_provider()
    return _provider


async def close_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.aclose()
        _provider = None
