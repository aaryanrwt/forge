"""OpenAI-compatible LLM provider adapter.

Supports the official OpenAI API and any OpenAI-compatible endpoint
(e.g. Azure OpenAI, vLLM, LM Studio) via the ``base_url`` parameter.
"""

from __future__ import annotations

import httpx

from forge.core.domain.exceptions import ConfigurationError, LLMProviderError
from forge.core.domain.models import TokenUsage
from forge.infrastructure.llm.base import BaseLLMProvider


class OpenAIAdapter(BaseLLMProvider):
    """Calls the OpenAI (or compatible) chat completions endpoint.

    Set ``FORGE_OPENAI_API_KEY`` in the environment to activate this provider.
    Override ``FORGE_OPENAI_BASE_URL`` to point at a compatible server.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        if not api_key:
            raise ConfigurationError("OpenAI API key is required")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> tuple[str, TokenUsage]:
        """Call the OpenAI chat completions endpoint.

        Args:
            messages: OpenAI-style message list.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Tuple of (response_text, TokenUsage).

        Raises:
            LLMProviderError: On HTTP or parsing errors.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            data = response.json()
            content: str = data["choices"][0]["message"]["content"]
            u = data.get("usage", {})
            usage = TokenUsage(
                prompt_tokens=u.get("prompt_tokens", 0),
                completion_tokens=u.get("completion_tokens", 0),
                total_tokens=u.get("total_tokens", 0),
            )
            return content, usage
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"OpenAI API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"OpenAI unexpected error: {exc}") from exc

    async def is_available(self) -> bool:
        """Return True if an API key is configured."""
        return bool(self._api_key)

    async def __aenter__(self) -> OpenAIAdapter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()
