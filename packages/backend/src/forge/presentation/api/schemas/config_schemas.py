"""Pydantic schemas for config/settings management endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ConfigResponse(BaseModel):
    """Exposes current Forge server configurations."""

    db_url: str
    llm_provider: str
    llm_model: str
    planner_type: str
    executor_timeout: int
    default_max_retries: int
    circuit_breaker_threshold: int
    circuit_breaker_timeout: int
    context_window_size: int
    plugins_dir: str
    log_level: str


class UpdateConfigRequest(BaseModel):
    """Allows runtime configuration changes (if supported by container/settings)."""

    llm_provider: Literal["ollama", "openai", "anthropic", "gemini"] | None = None
    llm_model: str | None = None
    planner_type: Literal["rule", "llm", "fallback"] | None = None
    executor_timeout: int | None = None
    default_max_retries: int | None = None
