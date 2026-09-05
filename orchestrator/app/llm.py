"""Pluggable OpenAI-compatible LLM providers (LiteLLM / vLLM shim / mock)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import httpx

from app.config import get_settings


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        ...

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        system = ""
        user_parts: list[str] = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                user_parts.append(f"{m.get('role', 'user')}: {m.get('content', '')}")
        return await self.complete(system or "You are ChatBot Avrone Due'Krey.", "\n".join(user_parts))

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        text = await self.chat(messages, model=model)
        # Simple chunking for SSE when upstream does not stream
        step = max(24, len(text) // 12 or 1)
        for i in range(0, len(text), step):
            yield text[i : i + step]


class MockLLMProvider(LLMProvider):
    """Deterministic stub used in tests and when execution is dry-run adjacent."""

    def __init__(self, response: Optional[str] = None):
        self.response = response
        self.calls: list[dict[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        if self.response is not None:
            return self.response
        return (
            f"[ChatBot Avrone Due'Krey · mock] "
            f"Understood. goal={user[:160]!r} — Sub-Agent Orchestration ready."
        )


class OpenAICompatibleProvider(LLMProvider):
    """Calls an OpenAI-compatible chat completions endpoint (LiteLLM default)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

    async def complete(self, system: str, user: str) -> str:
        return await self.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model or self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model or self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        import json

                        try:
                            data = json.loads(payload)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception:
            # Fall back to non-streaming
            text = await self.chat(messages, model=model)
            step = max(24, len(text) // 12 or 1)
            for i in range(0, len(text), step):
                yield text[i : i + step]


_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.allow_agent_execution:
            _provider = OpenAICompatibleProvider()
        else:
            _provider = MockLLMProvider()
    return _provider


def set_llm_provider(provider: LLMProvider) -> None:
    global _provider
    _provider = provider


def reset_llm_provider() -> None:
    global _provider
    _provider = None
