"""Anthropic Claude LLM provider adapter.

Calls the Anthropic Messages API.  System messages are extracted from the
messages list and sent in the dedicated ``system`` field, as required by the
Anthropic API specification.
"""

from __future__ import annotations

import httpx

from forge.core.domain.exceptions import ConfigurationError, LLMProviderError
from forge.core.domain.models import TokenUsage
from forge.infrastructure.llm.base import BaseLLMProvider


class AnthropicAdapter(BaseLLMProvider):
    """Calls the Anthropic Messages API.

    Set ``FORGE_ANTHROPIC_API_KEY`` in the environment to activate this
    provider.
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
    ) -> None:
        if not api_key:
            raise ConfigurationError("Anthropic API key is required")
        self._api_key = api_key
        self._model = model
        self._client = httpx.AsyncClient(
            headers={
                "x-api-key": api_key,
                "anthropic-version": self.ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            timeout=60.0,
        )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> tuple[str, TokenUsage]:
        """Call the Anthropic Messages endpoint.

        System messages are extracted and sent in the top-level ``system``
        field; all other messages are forwarded as-is.

        Args:
            messages: OpenAI-style message list (system/user/assistant).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Tuple of (response_text, TokenUsage).

        Raises:
            LLMProviderError: On HTTP or parsing errors.
        """
        system_content = ""
        filtered_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                # Concatenate multiple system messages if present
                system_content = (
                    f"{system_content}\n{msg['content']}".strip()
                    if system_content
                    else msg["content"]
                )
            else:
                filtered_messages.append(msg)

        payload: dict[str, object] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": filtered_messages,
        }
        if system_content:
            payload["system"] = system_content

        try:
            response = await self._client.post(self.API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            content: str = data["content"][0]["text"]
            u = data.get("usage", {})
            input_tokens: int = u.get("input_tokens", 0)
            output_tokens: int = u.get("output_tokens", 0)
            usage = TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
            return content, usage
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"Anthropic API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(f"Anthropic unexpected error: {exc}") from exc

    async def is_available(self) -> bool:
        """Return True if an Anthropic API key is configured."""
        return bool(self._api_key)

    async def __aenter__(self) -> AnthropicAdapter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()
