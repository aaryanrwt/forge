"""Forge domain interfaces — abstract contracts for all major components.

Every concrete implementation in the infrastructure and application layers
must satisfy one of these interfaces. This keeps the domain pure and enables
easy substitution for testing or alternative providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any
from uuid import UUID

from forge.core.domain.models import (
    ContextSummary,
    Execution,
    LogEntry,
    LogLevel,
    RetryDecision,
    Task,
    TaskType,
    TokenUsage,
    VerificationResult,
)


class IPlanner(ABC):
    """Decomposes a natural-language goal into an ordered list of Tasks."""

    @abstractmethod
    async def plan(self, goal: str) -> Execution:
        """Return a new Execution containing a planned task list for *goal*."""


class IExecutor(ABC):
    """Executes a single Task and returns it with status/outputs populated."""

    @abstractmethod
    async def execute(self, task: Task) -> Task:
        """Run *task* and return the mutated task with updated status/outputs."""

    @abstractmethod
    def supports(self, task_type: TaskType) -> bool:
        """Return True if this executor can handle *task_type*."""


class IVerifier(ABC):
    """Verifies whether a Task's execution was truly successful."""

    @abstractmethod
    async def verify(self, task: Task) -> VerificationResult:
        """Inspect *task* outputs and return a structured verdict."""


class IRetryController(ABC):
    """Decides whether and when to retry a failed Task."""

    @abstractmethod
    async def decide(self, task: Task, error: str | None = None) -> RetryDecision:
        """Return a RetryDecision given the current task state and optional error."""


class IMemoryRepository(ABC):
    """Persistent storage for executions, tasks, logs, and summaries."""

    # ── Execution ─────────────────────────────────────────────────────────────
    @abstractmethod
    async def save_execution(self, execution: Execution) -> None: ...

    @abstractmethod
    async def get_execution(self, execution_id: UUID) -> Execution | None: ...

    @abstractmethod
    async def list_executions(self, limit: int = 100) -> list[Execution]: ...

    # ── Task ──────────────────────────────────────────────────────────────────
    @abstractmethod
    async def save_task(self, task: Task) -> None: ...

    @abstractmethod
    async def get_task(self, task_id: UUID) -> Task | None: ...

    @abstractmethod
    async def get_tasks_by_execution(self, execution_id: UUID) -> list[Task]: ...

    # ── Logs ──────────────────────────────────────────────────────────────────
    @abstractmethod
    async def save_log(self, log: LogEntry) -> None: ...

    @abstractmethod
    async def get_logs(
        self,
        execution_id: UUID,
        limit: int = 100,
        level: LogLevel | None = None,
    ) -> list[LogEntry]: ...

    # ── Summaries ─────────────────────────────────────────────────────────────
    @abstractmethod
    async def save_summary(self, summary: ContextSummary) -> None: ...

    @abstractmethod
    async def get_summary(self, execution_id: UUID) -> ContextSummary | None: ...

    # ── Stats ─────────────────────────────────────────────────────────────────
    @abstractmethod
    async def get_execution_stats(self, execution_id: UUID) -> dict[str, Any]: ...


class IContextOptimizer(ABC):
    """Compresses conversation context to reduce LLM token usage."""

    @abstractmethod
    async def optimize(self, context: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_token_savings(self) -> int: ...


class IEventBus(ABC):
    """Pub/sub event bus for decoupled inter-component communication."""

    @abstractmethod
    async def publish(self, event: Any) -> None: ...

    @abstractmethod
    async def subscribe(self, event_type: type, handler: Callable) -> None: ...

    @abstractmethod
    async def unsubscribe(self, event_type: type, handler: Callable) -> None: ...


class ILLMProvider(ABC):
    """Abstraction over LLM providers (Ollama, OpenAI, Anthropic, Gemini)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier, e.g. 'ollama'."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The specific model being used, e.g. 'llama3.2'."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> tuple[str, TokenUsage]:
        """Send a chat completion request and return (text, token_usage)."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if the provider endpoint is reachable."""


class IPlugin(IExecutor, ABC):
    """Interface all Forge plugins must implement.

    Plugins are discovered from ``~/.forge/plugins/`` and registered with
    the PluginManager at startup.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def task_type(self) -> TaskType: ...

    @abstractmethod
    def supports(self, task_type: TaskType) -> bool: ...

    @abstractmethod
    async def execute(self, task: Task) -> Task: ...


class ILearningInterface(ABC):
    """Future learning / pattern-recognition interface (not implemented in v1).

    Kept in the domain layer so the orchestrator can depend on the abstraction
    without requiring a concrete implementation at this time.
    """

    @abstractmethod
    async def record_failure(self, task: Task, error: str) -> None: ...

    @abstractmethod
    async def record_success(self, task: Task) -> None: ...

    @abstractmethod
    async def get_suggestions(self, goal: str) -> list[dict[str, Any]]: ...
