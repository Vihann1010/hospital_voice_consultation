"""Provider factory and the LLMGateway.

The gateway is the ONLY door AI services use: it selects the model tier
(dialogue vs fast), applies caching, retries with timeouts, and meters cost —
so every stage gets the full resilience/cost stack for free.
"""
from dataclasses import replace
from typing import AsyncIterator, Dict, List, Optional

from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import (
    ChatRequest,
    CostLedger,
    LLMProvider,
    LLMResponse,
    ProviderError,
)
from app.ai.providers.cache import cache_key, response_cache
from app.ai.providers.cost import compute_cost_usd, cost_tracker
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.providers.resilience import retry_call, retry_stream
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TIER_DIALOGUE = "dialogue"
TIER_FAST = "fast"


def build_provider() -> LLMProvider:
    provider_name = settings.LLM_PROVIDER.lower().strip()
    if provider_name == "anthropic":
        return AnthropicProvider(base_url=settings.LLM_BASE_URL, api_key=settings.llm_api_key)
    if provider_name in {"sarvam", "openai", "custom", "groq", "together", "vllm"}:
        return OpenAICompatibleProvider(
            name=provider_name,
            base_url=settings.LLM_BASE_URL,
            api_key=settings.llm_api_key,
            supports_json_mode=settings.LLM_SUPPORTS_JSON_MODE,
        )
    raise ValueError(
        f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. "
        "Use one of: sarvam, openai, anthropic, groq, together, vllm, custom."
    )


class LLMGateway:
    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self.provider = provider or build_provider()
        logger.info("llm_gateway_ready", extra={"provider": self.provider.name})

    def _model_for(self, tier: str) -> str:
        return settings.llm_fast_model if tier == TIER_FAST else settings.LLM_MODEL

    async def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        stage: str,
        tier: str = TIER_FAST,
        temperature: float = 0.2,
        max_tokens: int = 900,
        json_mode: bool = True,
        cache_ttl_s: Optional[int] = None,
        ledger: Optional[CostLedger] = None,
        tag: str = "-",
    ) -> LLMResponse:
        request = ChatRequest(
            messages=messages,
            model=self._model_for(tier),
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        key = ""
        cacheable = cache_ttl_s is not None and temperature <= 0.3
        if cacheable:
            key = cache_key(self.provider.name, request, extra=stage)
            hit = response_cache.get(key)
            if hit is not None:
                cost_tracker.record(hit, stage=stage, tag=tag)
                if ledger is not None:
                    ledger.add(hit, stage=stage, cost_usd=0.0)
                return hit

        try:
            response = await retry_call(lambda: self.provider.complete(request), op=stage)
        except ProviderError:
            # Tiers are a cost optimisation, not a requirement. If the dialogue
            # model is unavailable — wrong name, no access on this key, a
            # provider-side outage — a summary written by the cheaper model is
            # far better than no summary, so fall back rather than lose the
            # stage entirely.
            fallback_model = self._model_for(TIER_FAST)
            if tier != TIER_FAST and fallback_model != request.model:
                logger.warning(
                    "llm_tier_fallback",
                    extra={"stage": stage, "from_model": request.model,
                           "to_model": fallback_model},
                )
                request = replace(request, model=fallback_model)
                response = await retry_call(
                    lambda: self.provider.complete(request), op=f"{stage}_fallback"
                )
            else:
                raise
        cost = cost_tracker.record(response, stage=stage, tag=tag)
        if ledger is not None:
            ledger.add(response, stage=stage, cost_usd=cost)
        if cacheable:
            response_cache.put(key, response, ttl_s=cache_ttl_s)
        return response

    async def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        stage: str,
        tier: str = TIER_DIALOGUE,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = True,
        ledger: Optional[CostLedger] = None,
        tag: str = "-",
    ) -> AsyncIterator[str]:
        request = ChatRequest(
            messages=messages,
            model=self._model_for(tier),
            temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
            max_tokens=settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens,
            json_mode=json_mode,
        )
        collected: List[str] = []

        def open_stream() -> AsyncIterator[str]:
            return self.provider.stream(request)

        async for delta in retry_stream(open_stream, op=stage):
            collected.append(delta)
            yield delta

        # Streams rarely report usage; estimate for cost visibility.
        text = "".join(collected)
        estimate = LLMResponse(
            text=text,
            model=request.model,
            provider=self.provider.name,
            input_tokens=sum(len(m.get("content", "")) for m in messages) // 4,
            output_tokens=max(1, len(text) // 4),
        )
        cost = cost_tracker.record(estimate, stage=stage, tag=tag)
        if ledger is not None:
            ledger.add(estimate, stage=stage, cost_usd=cost)

    async def aclose(self) -> None:
        await self.provider.aclose()


_gateway: Optional[LLMGateway] = None


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway


async def close_gateway() -> None:
    global _gateway
    if _gateway is not None:
        await _gateway.aclose()
        _gateway = None


def cost_usd_hint(input_tokens: int, output_tokens: int) -> float:
    return compute_cost_usd(input_tokens, output_tokens)
