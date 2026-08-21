"""OpenAI-compatible chat provider.

Covers Sarvam (`https://api.sarvam.ai/v1`), OpenAI, Groq, Together, Azure
OpenAI-compatible gateways, and self-hosted vLLM — anything speaking the
`/chat/completions` wire format with SSE streaming.
"""
import json
import time
from typing import AsyncIterator

import httpx

from app.ai.providers.base import ChatRequest, LLMProvider, LLMResponse, estimate_tokens
from app.ai.providers.resilience import classify_http_error
from app.core.config import settings


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, *, name: str, base_url: str, api_key: str, supports_json_mode: bool) -> None:
        self.name = name
        self.supports_json_mode = supports_json_mode
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(
                settings.LLM_REQUEST_TIMEOUT_S, connect=settings.LLM_CONNECT_TIMEOUT_S
            ),
            headers={
                "Authorization": f"Bearer {api_key}",
                # Sarvam accepts its subscription key on this header; other
                # OpenAI-compatible vendors simply ignore it.
                "api-subscription-key": api_key,
            },
        )

    def _payload(self, request: ChatRequest, stream: bool) -> dict:
        payload: dict = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.json_mode and self.supports_json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def complete(self, request: ChatRequest) -> LLMResponse:
        started = time.perf_counter()
        try:
            response = await self._client.post(
                "/chat/completions", json=self._payload(request, stream=False)
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise classify_http_error(exc) from exc
        body = response.json()
        text = (body["choices"][0]["message"].get("content") or "").strip()
        usage = body.get("usage") or {}
        prompt_chars = sum(len(m.get("content", "")) for m in request.messages)
        return LLMResponse(
            text=text,
            model=body.get("model", request.model),
            provider=self.name,
            input_tokens=int(usage.get("prompt_tokens") or estimate_tokens("x" * prompt_chars)),
            output_tokens=int(usage.get("completion_tokens") or estimate_tokens(text)),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=self._payload(request, stream=True)
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
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise classify_http_error(exc) from exc

    async def aclose(self) -> None:
        await self._client.aclose()
