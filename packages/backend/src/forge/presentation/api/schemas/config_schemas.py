"""Pydantic schemas for config/settings management endpoint."""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


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
    llm_provider: Optional[Literal["ollama", "openai", "anthropic", "gemini"]] = None
    llm_model: Optional[str] = None
    planner_type: Optional[Literal["rule", "llm", "fallback"]] = None
    executor_timeout: Optional[int] = None
    default_max_retries: Optional[int] = None
