"""Forge domain exceptions — custom exception hierarchy.

All Forge-specific exceptions derive from ForgeError, enabling catch-all
handling at the application boundary while preserving granular semantics
throughout the lower layers.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID


class ForgeError(Exception):
    """Base exception for all Forge errors."""


class PlannerError(ForgeError):
    """Raised when goal planning fails (LLM error, parse error, etc.)."""


class ExecutorError(ForgeError):
    """Raised when task execution encounters an unrecoverable error."""


class VerificationError(ForgeError):
    """Raised when task verification setup is invalid."""


class RetryBudgetExhausted(ForgeError):
    """Raised when a task has exceeded its retry budget."""

    def __init__(
        self,
        message: str,
        task_id: Optional[UUID] = None,
        max_retries: int = 0,
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.max_retries = max_retries


class CircuitBreakerOpen(ForgeError):
    """Raised when a circuit breaker is open for an executor."""

    def __init__(
        self,
        message: str,
        executor_name: str = "",
        failure_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.executor_name = executor_name
        self.failure_count = failure_count


class InfiniteLoopDetected(ForgeError):
    """Raised when an infinite retry loop is detected via cycle hash."""

    def __init__(
        self,
        message: str,
        task_id: Optional[UUID] = None,
        cycle_hash: str = "",
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.cycle_hash = cycle_hash


class MCPConnectionError(ForgeError):
    """Raised when MCP transport connection or communication fails."""


class LLMProviderError(ForgeError):
    """Raised when an LLM provider call fails (network, auth, quota)."""


class PluginError(ForgeError):
    """Raised when a plugin fails to load or execute."""


class ConfigurationError(ForgeError):
    """Raised when Forge configuration is invalid or incomplete."""
