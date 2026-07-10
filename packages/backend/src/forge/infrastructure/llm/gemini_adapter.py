"""Google Gemini LLM provider adapter.

Calls the Google Generative Language REST API (v1beta).  Messages are
converted from OpenAI-style role/content dicts to Gemini's ``contents``
format, mapping 'assistant' → 'model' and 'system' → 'user'.
"""
from __future__ import annotations

from typing import Any, Dict, List

import httpx

from forge.core.domain.exceptions import ConfigurationError, LLMProviderError
from forge.core.domain.models import TokenUsage
from forge.infrastructure.llm.base import BaseLLMProvider


class GeminiAdapter(BaseLLMProvider):
    """Calls the Google Generative Language API (Gemini).

    Set ``FORGE_GEMINI_API_KEY`` in the environment to activate this provider.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
    ) -> None:
        if not api_key:
            raise ConfigurationError("Gemini API key is required")
        self._api_key = api_key
        self._model = model
        self._client = httpx.AsyncClient(timeout=60.0)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _to_gemini_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style messages to Gemini contents format.

        Gemini uses ``{"role": "user"|"model", "parts": [{"text": "..."}]}``.
        System messages are mapped to 'user' role since Gemini does not have
        a dedicated system role in the REST API.
        """
        role_map: Dict[str, str] = {
            "user": "user",
            "assistant": "model",
            "system": "user",
        }
        contents: List[Dict[str, Any]] = []
        for msg in messages:
            role = role_map.get(msg.get("role", "user"), "user")
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}],
            })
        return contents

    async def complete(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> tuple[str, TokenUsage]:
        """Call the Gemini generateContent endpoint.

        Args:
            messages: OpenAI-style message list.
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.

        Returns:
            Tuple of (response_text, TokenUsage).

        Raises:
            LLMProviderError: On HTTP or parsing errors.
        """
        url = f"{self.BASE_URL}/{self._model}:generateContent?key={self._api_key}"
        payload: Dict[str, Any] = {
            "contents": self._to_gemini_messages(messages),
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            content: str = data["candidates"][0]["content"]["parts"][0]["text"]
            u = data.get("usageMetadata", {})
            prompt_tokens: int = u.get("promptTokenCount", 0)
            completion_tokens: int = u.get("candidatesTokenCount", 0)
            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            return content, usage
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"Gemini API error {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"Gemini unexpected error: {exc}") from exc

    async def is_available(self) -> bool:
        """Return True if a Gemini API key is configured."""
        return bool(self._api_key)

    async def __aenter__(self) -> "GeminiAdapter":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()
