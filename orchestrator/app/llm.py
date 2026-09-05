"""Pluggable OpenAI-compatible LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.config import get_settings


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        ...


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
            f"[mock-llm] role_context={system[:80]!r} "
            f"goal={user[:120]!r} — completed successfully."
        )


class OpenAICompatibleProvider(LLMProvider):
    """Calls an OpenAI-compatible chat completions endpoint."""

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
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


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
