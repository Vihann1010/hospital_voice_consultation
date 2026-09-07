"""Provider-agnostic LLM contracts.

Every AI service in the platform talks to `LLMGateway` (see factory.py), which
delegates to an `LLMProvider` implementation. Swapping vendors is a config
change (LLM_PROVIDER), never a code change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional


@dataclass(frozen=True)
class ChatRequest:
    messages: List[Dict[str, str]]
    model: str
    temperature: float = 0.3
    max_tokens: int = 800
    json_mode: bool = False
    stop: Optional[List[str]] = None


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False


class ProviderError(Exception):
    """Non-retryable provider failure (bad request, auth, quota exhausted)."""


class RetryableProviderError(ProviderError):
    """Transient failure worth retrying (timeout, 429, 5xx, connection reset)."""


def estimate_tokens(text: str) -> int:
    """Cheap fallback when a provider omits usage data (~4 chars/token)."""
    return max(1, len(text) // 4)


@dataclass
class CostLedger:
    """Per-consultation accumulation of token usage and spend."""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0
    by_stage: Dict[str, int] = field(default_factory=dict)

    def add(self, response: LLMResponse, *, stage: str, cost_usd: float) -> None:
        self.input_tokens += response.input_tokens
        self.output_tokens += response.output_tokens
        self.calls += 1
        self.cost_usd += cost_usd
        self.by_stage[stage] = self.by_stage.get(stage, 0) + 1

    def snapshot(self) -> Dict[str, object]:
        return {
            "llm_calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.cost_usd, 6),
            "calls_by_stage": dict(self.by_stage),
        }


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def complete(self, request: ChatRequest) -> LLMResponse:
        """Single-shot completion returning the full text + usage."""

    @abstractmethod
    def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Yield content deltas as they arrive."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release network resources."""
