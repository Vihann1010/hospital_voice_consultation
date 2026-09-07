"""Base class for pipeline services.

Guarantees the "structured JSON only" contract: every call goes out with an
explicit JSON schema in the prompt (plus provider json_mode when supported),
the reply is parsed and validated against the stage's Pydantic model, and a
failed parse triggers exactly one self-repair round that feeds the validation
errors back to the model. A second failure raises StageError — callers decide
whether the stage is critical or degradable.

`run_json` raises StageError for EVERY failure mode, including provider
outages (rate limits, quota exhaustion, timeouts). Callers therefore need to
handle one exception type, and a single unavailable stage costs that section
rather than the whole pipeline.
"""
import json
import re
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.providers.base import CostLedger, ProviderError
from app.ai.providers.factory import LLMGateway, get_gateway
from app.core.logging import get_logger

logger = get_logger(__name__)

OutputT = TypeVar("OutputT", bound=BaseModel)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class StageError(Exception):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = _FENCE.sub("", text.strip()).strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = _OBJECT.search(text)
        if match:
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
    return None


class BaseAIService(Generic[OutputT]):
    stage: str = "base"
    tier: str = "fast"           # cost optimization: cheap model unless overridden
    temperature: float = 0.15
    max_tokens: int = 900
    output_model: Type[OutputT]

    def __init__(self, gateway: Optional[LLMGateway] = None) -> None:
        self.gateway = gateway or get_gateway()

    def _json_contract(self) -> str:
        schema = self.output_model.model_json_schema()
        return (
            "Respond with EXACTLY one valid JSON object and nothing else — no prose, "
            "no markdown fences. It must conform to this JSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False)
        )

    async def run_json(
        self,
        *,
        system: str,
        user: str,
        ledger: Optional[CostLedger] = None,
        tag: str = "-",
        cache_ttl_s: Optional[int] = None,
    ) -> OutputT:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": f"{system}\n\n{self._json_contract()}"},
            {"role": "user", "content": user},
        ]
        try:
            response = await self.gateway.complete(
                messages,
                stage=self.stage,
                tier=self.tier,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                json_mode=True,
                cache_ttl_s=cache_ttl_s,
                ledger=ledger,
                tag=tag,
            )
        except ProviderError as exc:
            # Callers are documented to handle StageError and degrade around a
            # failed stage. A provider outage — rate limit, quota exhaustion,
            # timeout — must therefore surface as a StageError too, or it
            # escapes every handler and takes the whole pipeline down with it
            # instead of costing one section.
            raise StageError(self.stage, f"provider unavailable: {exc}") from exc
        result = self._validate(response.text)
        if result is not None:
            return result

        # One self-repair round with the concrete failure fed back.
        error_detail = self._validation_error(response.text)
        logger.warning(
            "stage_output_invalid", extra={"stage": self.stage, "error": error_detail[:300]}
        )
        repair_messages = messages + [
            {"role": "assistant", "content": response.text[:4000]},
            {
                "role": "user",
                "content": (
                    "Your previous reply was not valid against the required JSON schema. "
                    f"Problems: {error_detail[:800]}\n"
                    "Reply again with ONLY the corrected JSON object."
                ),
            },
        ]
        try:
            repair = await self.gateway.complete(
                repair_messages,
                stage=f"{self.stage}_repair",
                tier=self.tier,
                temperature=0.0,
                max_tokens=self.max_tokens,
                json_mode=True,
                ledger=ledger,
                tag=tag,
            )
        except ProviderError as exc:
            raise StageError(self.stage, f"provider unavailable during repair: {exc}") from exc
        result = self._validate(repair.text)
        if result is not None:
            return result
        raise StageError(self.stage, f"unparseable output after repair: {repair.text[:200]}")

    def _validate(self, text: str) -> Optional[OutputT]:
        payload = parse_json_object(text)
        if payload is None:
            return None
        try:
            return self.output_model.model_validate(payload)
        except ValidationError:
            return None

    def _validation_error(self, text: str) -> str:
        payload = parse_json_object(text)
        if payload is None:
            return "reply was not a JSON object"
        try:
            self.output_model.model_validate(payload)
            return "unknown"
        except ValidationError as exc:
            return "; ".join(
                f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()[:6]
            )
