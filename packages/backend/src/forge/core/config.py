"""Forge configuration — pydantic-settings based, env-var driven.

All settings are prefixed with FORGE_ and can be overridden via environment
variables or a .env file in the working directory. A singleton accessor
``get_settings()`` is provided for dependency injection throughout the app.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ForgeSettings(BaseSettings):
    """All Forge runtime configuration.

    Environment variable prefix: ``FORGE_``
    """

    model_config = SettingsConfigDict(
        env_prefix="FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    db_url: str = Field(
        default="sqlite+aiosqlite:///./forge.db",
        description="SQLAlchemy async database URL",
    )

    # ── Server ───────────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0", description="API server host")
    port: int = Field(default=8000, description="API server port")
    debug: bool = Field(default=False, description="Enable debug/reload mode")
    cors_origins: List[str] = Field(default=["*"], description="Allowed CORS origins")

    # ── LLM Provider ─────────────────────────────────────────────────────────
    llm_provider: Literal["ollama", "openai", "anthropic", "gemini"] = Field(
        default="ollama",
        description="Default LLM provider. Ollama requires no API key.",
    )
    llm_model: str = Field(default="llama3.2", description="Model name for the provider")

    # Ollama (default — no API key required)
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL",
    )

    # OpenAI (optional)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI-compatible API base URL",
    )

    # Anthropic (optional)
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    anthropic_model: str = Field(
        default="claude-3-haiku-20240307",
        description="Anthropic model name",
    )

    # Gemini (optional)
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    gemini_model: str = Field(default="gemini-1.5-flash", description="Gemini model name")

    # ── Planner ──────────────────────────────────────────────────────────────
    planner_type: Literal["rule", "llm", "fallback"] = Field(
        default="fallback",
        description=(
            "Planner strategy: 'rule'=deterministic offline, "
            "'llm'=LLM-powered, 'fallback'=LLM then rule"
        ),
    )

    # ── Executor ─────────────────────────────────────────────────────────────
    executor_timeout: int = Field(default=300, description="Default executor timeout (seconds)")
    shell_executor_timeout: int = Field(default=60, description="Shell executor timeout")
    docker_executor_timeout: int = Field(default=600, description="Docker executor timeout")
    python_executor_timeout: int = Field(default=60, description="Python executor timeout")
    git_executor_timeout: int = Field(default=120, description="Git executor timeout")

    # ── Retry ─────────────────────────────────────────────────────────────────
    default_max_retries: int = Field(default=3, description="Default max retries per task")
    retry_initial_delay: float = Field(default=1.0, description="Initial retry delay (seconds)")
    retry_max_delay: float = Field(default=60.0, description="Maximum retry delay (seconds)")
    retry_backoff_factor: float = Field(default=2.0, description="Exponential backoff multiplier")
    circuit_breaker_threshold: int = Field(
        default=5,
        description="Consecutive failures before circuit opens",
    )
    circuit_breaker_timeout: int = Field(
        default=60,
        description="Seconds before circuit attempts half-open",
    )

    # ── Context ───────────────────────────────────────────────────────────────
    max_context_tokens: int = Field(
        default=8000,
        description="Maximum context tokens before compression",
    )
    context_window_size: int = Field(
        default=10,
        description="Number of recent entries to keep in sliding window",
    )

    # ── Plugins ───────────────────────────────────────────────────────────────
    plugins_dir: Path = Field(
        default_factory=lambda: Path.home() / ".forge" / "plugins",
        description="Directory to discover Forge plugins from",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: Literal["json", "text"] = Field(
        default="text",
        description="Log output format: 'text' or 'json'",
    )


_settings: Optional[ForgeSettings] = None


def get_settings() -> ForgeSettings:
    """Return the singleton ForgeSettings instance.

    Reads environment variables and .env file on first call; subsequent
    calls return the cached instance.
    """
    global _settings
    if _settings is None:
        _settings = ForgeSettings()
    return _settings


def reset_settings() -> None:
    """Reset the settings singleton.

    Useful in tests that need to vary configuration between test cases.
    """
    global _settings
    _settings = None
