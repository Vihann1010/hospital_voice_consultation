"""Global cost accounting: every gateway call is metered and logged.

Per-consultation figures live in `CostLedger` (providers/base.py) and are
written into the clinical dossier; this module keeps process-wide totals and
computes spend from the configured per-1M-token rates.
"""
import threading
from typing import Dict

from app.ai.providers.base import LLMResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def compute_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * settings.LLM_INPUT_COST_PER_MTOK
        + output_tokens * settings.LLM_OUTPUT_COST_PER_MTOK
    ) / 1_000_000.0


class CostTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.cached_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.by_stage: Dict[str, int] = {}

    def record(self, response: LLMResponse, *, stage: str, tag: str) -> float:
        cost = 0.0 if response.cached else compute_cost_usd(
            response.input_tokens, response.output_tokens
        )
        with self._lock:
            self.calls += 1
            if response.cached:
                self.cached_calls += 1
            else:
                self.input_tokens += response.input_tokens
                self.output_tokens += response.output_tokens
                self.cost_usd += cost
            self.by_stage[stage] = self.by_stage.get(stage, 0) + 1
        logger.info(
            "llm_call",
            extra={
                "stage": stage,
                "tag": tag,
                "provider": response.provider,
                "model": response.model,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "latency_ms": round(response.latency_ms, 1),
                "cached": response.cached,
                "cost_usd": round(cost, 6),
            },
        )
        return cost

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "calls": self.calls,
                "cached_calls": self.cached_calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cost_usd": round(self.cost_usd, 4),
                "by_stage": dict(self.by_stage),
            }


cost_tracker = CostTracker()
