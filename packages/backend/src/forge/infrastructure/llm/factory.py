"""Factory function to instantiate the configured LLM provider.

Reads the ``llm_provider`` field from ForgeSettings and constructs the
appropriate adapter.  Raises ``ConfigurationError`` for unknown providers or
missing required API keys.
"""
from __future__ import annotations

from forge.core.domain.exceptions import ConfigurationError
from forge.infrastructure.llm.anthropic_adapter import AnthropicAdapter
from forge.infrastructure.llm.base import BaseLLMProvider
from forge.infrastructure.llm.gemini_adapter import GeminiAdapter
from forge.infrastructure.llm.ollama_adapter import OllamaAdapter
from forge.infrastructure.llm.openai_adapter import OpenAIAdapter


def create_llm_provider(settings: object) -> BaseLLMProvider:
    """Instantiate the LLM provider specified in *settings*.

    Args:
        settings: A ``ForgeSettings`` instance (typed as ``object`` to avoid
                  a hard import cycle between infrastructure and core/config).

    Returns:
        A fully configured ``BaseLLMProvider``.

    Raises:
        ConfigurationError: If the provider is unknown or a required API key
                            is missing.
    """
    provider: str = getattr(settings, "llm_provider", "ollama")

    if provider == "ollama":
        return OllamaAdapter(
            base_url=getattr(settings, "ollama_base_url", "http://localhost:11434"),
            model=getattr(settings, "llm_model", "llama3.2"),
        )

    if provider == "openai":
        api_key: str | None = getattr(settings, "openai_api_key", None)
        if not api_key:
            raise ConfigurationError(
                "FORGE_OPENAI_API_KEY environment variable is required for the OpenAI provider."
            )
        return OpenAIAdapter(
            api_key=api_key,
            model=getattr(settings, "openai_model", "gpt-4o-mini"),
            base_url=getattr(settings, "openai_base_url", "https://api.openai.com/v1"),
        )

    if provider == "anthropic":
        api_key = getattr(settings, "anthropic_api_key", None)
        if not api_key:
            raise ConfigurationError(
                "FORGE_ANTHROPIC_API_KEY environment variable is required for the Anthropic provider."
            )
        return AnthropicAdapter(
            api_key=api_key,
            model=getattr(settings, "anthropic_model", "claude-3-haiku-20240307"),
        )

    if provider == "gemini":
        api_key = getattr(settings, "gemini_api_key", None)
        if not api_key:
            raise ConfigurationError(
                "FORGE_GEMINI_API_KEY environment variable is required for the Gemini provider."
            )
        return GeminiAdapter(
            api_key=api_key,
            model=getattr(settings, "gemini_model", "gemini-1.5-flash"),
        )

    raise ConfigurationError(
        f"Unknown LLM provider: '{provider}'. "
        f"Valid values: 'ollama', 'openai', 'anthropic', 'gemini'."
    )
