"""Ollama LLM provider adapter — default provider, no API key required.

Connects to a locally-running Ollama instance (default: http://localhost:11434)
and calls the /api/chat endpoint using the chat completion protocol.
"""
from __future__ import annotations

from typing import Dict, List

import httpx

from forge.core.domain.exceptions import LLMProviderError
from forge.core.domain.models import TokenUsage
from forge.infrastructure.llm.base import BaseLLMProvider


class OllamaAdapter(BaseLLMProvider):
    """Calls Ollama's /api/chat endpoint.

    Ollama is the *default* provider because it requires no API key and runs
    fully locally.  Install Ollama from https://ollama.com and pull a model
    (e.g. ``ollama pull llama3.2``) before using this adapter.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> tuple[str, TokenUsage]:
        """Send a chat completion request to Ollama.

        Args:
            messages: OpenAI-style list of {'role': ..., 'content': ...} dicts.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature (0.0–1.0).

        Returns:
            A tuple of (response_text, TokenUsage).

        Raises:
            LLMProviderError: On any HTTP or parsing error.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            content: str = data.get("message", {}).get("content", "")
            prompt_tokens: int = data.get("prompt_eval_count", 0)
            completion_tokens: int = data.get("eval_count", 0)
            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            return content, usage
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama request failed: {exc}") from exc
        except Exception as exc:
            raise LLMProviderError(f"Ollama unexpected error: {exc}") from exc

    async def is_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api/tags",
                timeout=2.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def __aenter__(self) -> "OllamaAdapter":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()
