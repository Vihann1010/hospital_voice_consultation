"""Anthropic Messages API provider (streaming + completion), no SDK required."""
import json
import time
from typing import AsyncIterator, Dict, List, Tuple

import httpx

from app.ai.providers.base import ChatRequest, LLMProvider, LLMResponse, estimate_tokens
from app.ai.providers.resilience import classify_http_error
from app.core.config import settings


def _split_system(messages: List[Dict[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    if not rest:  # Anthropic requires at least one user message
        rest = [{"role": "user", "content": "Begin."}]
    return "\n\n".join(system_parts), rest


class AnthropicProvider(LLMProvider):
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.name = "anthropic"
        self._client = httpx.AsyncClient(
            base_url=base_url or "https://api.anthropic.com",
            timeout=httpx.Timeout(
                settings.LLM_REQUEST_TIMEOUT_S, connect=settings.LLM_CONNECT_TIMEOUT_S
            ),
            headers={
                "x-api-key": api_key,
                "anthropic-version": settings.ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
        )

    def _payload(self, request: ChatRequest, stream: bool) -> dict:
        system, messages = _split_system(request.messages)
        if request.json_mode:
            system = f"{system}\n\nRespond with a single valid JSON object and nothing else."
        payload: dict = {
            "model": request.model,
            "system": system,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.stop:
            payload["stop_sequences"] = request.stop
        return payload

    async def complete(self, request: ChatRequest) -> LLMResponse:
        started = time.perf_counter()
        try:
            response = await self._client.post("/v1/messages", json=self._payload(request, False))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise classify_http_error(exc) from exc
        body = response.json()
        text = "".join(
            block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
        ).strip()
        usage = body.get("usage") or {}
        return LLMResponse(
            text=text,
            model=body.get("model", request.model),
            provider=self.name,
            input_tokens=int(usage.get("input_tokens") or 0) or estimate_tokens(str(request.messages)),
            output_tokens=int(usage.get("output_tokens") or 0) or estimate_tokens(text),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST", "/v1/messages", json=self._payload(request, True)
            ) as response:
                if response.status_code >= 400:
                    # The body is not read yet on a streaming response, so
                    # raise_for_status() alone would leave classify_http_error()
                    # unable to read exc.response.text (httpx.ResponseNotRead).
                    # Read it here, while the response is still open, so the
                    # provider's actual error message survives.
                    await response.aread()
                    response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield delta["text"]
                    elif event.get("type") == "message_stop":
                        return
        except httpx.HTTPError as exc:
            raise classify_http_error(exc) from exc

    async def aclose(self) -> None:
        await self._client.aclose()
