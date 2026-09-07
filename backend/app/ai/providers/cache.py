"""In-process TTL + LRU cache for LLM responses.

Only low-temperature, deterministic-by-intent calls opt in (patient education,
investigation recommendations, repeated extraction of identical transcripts) —
dialogue turns are never cached. Keys are SHA-256 over the full request shape,
so a provider/model/prompt change can never serve a stale answer.
"""
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import replace
from typing import Optional

from app.ai.providers.base import ChatRequest, LLMResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def cache_key(provider: str, request: ChatRequest, extra: str = "") -> str:
    payload = json.dumps(
        {
            "p": provider,
            "m": request.model,
            "msgs": request.messages,
            "t": request.temperature,
            "mt": request.max_tokens,
            "j": request.json_mode,
            "x": extra,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, max_entries: Optional[int] = None) -> None:
        self._store: "OrderedDict[str, tuple[float, LLMResponse]]" = OrderedDict()
        self._max = max_entries or settings.AI_CACHE_MAX_ENTRIES
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[LLMResponse]:
        if not settings.AI_CACHE_ENABLED:
            return None
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        expires_at, response = entry
        if expires_at < time.monotonic():
            del self._store[key]
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return replace(response, cached=True)

    def put(self, key: str, response: LLMResponse, ttl_s: Optional[int] = None) -> None:
        if not settings.AI_CACHE_ENABLED or response.cached:
            return
        self._store[key] = (time.monotonic() + (ttl_s or settings.AI_CACHE_TTL_S), response)
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            evicted, _ = self._store.popitem(last=False)
            logger.debug("ai_cache_evict", extra={"key": evicted[:12]})

    def stats(self) -> dict:
        return {"entries": len(self._store), "hits": self.hits, "misses": self.misses}


response_cache = ResponseCache()
