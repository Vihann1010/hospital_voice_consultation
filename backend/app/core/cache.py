"""Shared cache / coordination layer.

An in-process cache backs rate limiting, response caching, idempotency, and the
delivery-retry lock. Every cache concern in the platform goes through this
interface.

The in-memory backend is deliberately honest about its limits: it reports
`distributed = False`, and the readiness endpoint surfaces that so an operator
running multiple replicas can see that limits are per-process.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)

class CacheBackend(ABC):
    distributed: bool = False
    name: str = "abstract"

    @abstractmethod
    async def get(self, key: str) -> Optional[str]: ...

    @abstractmethod
    async def set(self, key: str, value: str, ttl_s: Optional[int] = None) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def incr_with_ttl(self, key: str, ttl_s: int) -> Tuple[int, int]:
        """Increment a counter, setting its TTL on first use.

        Returns (count, seconds_remaining) — everything a fixed-window rate
        limiter needs from a single round trip.
        """

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class InMemoryCache(CacheBackend):
    distributed = False
    name = "in-memory"

    def __init__(self) -> None:
        self._values: dict = {}
        self._lock = asyncio.Lock()

    def _purge(self) -> None:
        now = time.monotonic()
        expired = [key for key, (_, expiry) in self._values.items()
                   if expiry is not None and expiry < now]
        for key in expired:
            del self._values[key]

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if expiry is not None and expiry < time.monotonic():
                del self._values[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl_s: Optional[int] = None) -> None:
        async with self._lock:
            if len(self._values) > 10000:
                self._purge()
            expiry = time.monotonic() + ttl_s if ttl_s else None
            self._values[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._values.pop(key, None)

    async def incr_with_ttl(self, key: str, ttl_s: int) -> Tuple[int, int]:
        async with self._lock:
            now = time.monotonic()
            entry = self._values.get(key)
            if entry is None or (entry[1] is not None and entry[1] < now):
                self._values[key] = ("1", now + ttl_s)
                return 1, ttl_s
            count = int(entry[0]) + 1
            self._values[key] = (str(count), entry[1])
            remaining = int((entry[1] or now) - now)
            return count, max(remaining, 0)


_backend: Optional[CacheBackend] = None


def get_cache() -> CacheBackend:
    global _backend
    if _backend is None:
        _backend = InMemoryCache()
        logger.info("cache_backend_ready", extra={"backend": "in-memory"})
    return _backend


async def close_cache() -> None:
    global _backend
    if _backend is not None:
        await _backend.aclose()
        _backend = None
