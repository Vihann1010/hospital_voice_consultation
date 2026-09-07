"""Resilience policy: classification of transient errors + retry helpers.

Rules:
- Completions retry on timeouts, connection errors, HTTP 408/429/5xx with
  exponential backoff and jitter (LLM_MAX_RETRIES attempts total).
- Streams retry only while establishing the connection; once the first token
  has been delivered downstream, errors propagate (we never replay speech).
"""
import asyncio
import random
from typing import AsyncIterator, Awaitable, Callable, TypeVar

import httpx

from app.ai.providers.base import ProviderError, RetryableProviderError
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def classify_http_error(exc: Exception) -> ProviderError:
    """Map transport/HTTP failures onto retryable vs terminal errors."""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return RetryableProviderError(f"transport: {exc!r}")
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = exc.response.text[:300]
        if status in RETRYABLE_STATUS:
            return RetryableProviderError(f"http {status}: {body}")
        return ProviderError(f"http {status}: {body}")
    return ProviderError(repr(exc))


def _backoff_delay(attempt: int) -> float:
    base = settings.LLM_RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
    capped = min(base, settings.LLM_RETRY_MAX_DELAY_S)
    return capped * (0.5 + random.random() / 2)  # full jitter


async def retry_call(fn: Callable[[], Awaitable[T]], *, op: str) -> T:
    """Run `fn` with the platform retry policy and an overall per-attempt timeout."""
    last: Exception = RetryableProviderError("no attempts made")
    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(fn(), timeout=settings.LLM_REQUEST_TIMEOUT_S)
        except asyncio.TimeoutError:
            last = RetryableProviderError(f"{op}: attempt timed out")
        except RetryableProviderError as exc:
            last = exc
        except ProviderError:
            raise
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            mapped = classify_http_error(exc)
            if not isinstance(mapped, RetryableProviderError):
                raise mapped from exc
            last = mapped
        if attempt < settings.LLM_MAX_RETRIES:
            delay = _backoff_delay(attempt)
            logger.warning(
                "llm_retry",
                extra={"op": op, "attempt": attempt, "delay_s": round(delay, 2), "error": str(last)},
            )
            await asyncio.sleep(delay)
    raise last


async def retry_stream(
    open_stream: Callable[[], AsyncIterator[str]], *, op: str
) -> AsyncIterator[str]:
    """Retry stream establishment; after the first yielded token, no replays."""
    attempt = 0
    while True:
        attempt += 1
        yielded_any = False
        try:
            async for delta in open_stream():
                yielded_any = True
                yield delta
            return
        except (ProviderError, httpx.HTTPError, asyncio.TimeoutError) as exc:
            mapped = (
                exc
                if isinstance(exc, ProviderError)
                else classify_http_error(exc)
                if isinstance(exc, httpx.HTTPError)
                else RetryableProviderError("stream connect timeout")
            )
            retryable = isinstance(mapped, RetryableProviderError)
            if yielded_any or not retryable or attempt >= settings.LLM_MAX_RETRIES:
                raise mapped if isinstance(mapped, ProviderError) else ProviderError(repr(exc))
            delay = _backoff_delay(attempt)
            logger.warning(
                "llm_stream_retry",
                extra={"op": op, "attempt": attempt, "delay_s": round(delay, 2), "error": str(mapped)},
            )
            await asyncio.sleep(delay)
