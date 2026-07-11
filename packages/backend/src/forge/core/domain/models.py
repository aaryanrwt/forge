"""Forge domain models — pure Pydantic v2 data structures.

These models are the heart of the domain layer. They carry no infrastructure
dependencies and are safe to use in any layer. All persistence mapping is
done in the infrastructure layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ── Enums ────────────────────────────────────────────────────────────────────


class TaskStatus(StrEnum):
    """Lifecycle states for a Task or Execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    """Supported executor kinds."""

    CLI = "cli"
    PYTHON = "python"
    MCP = "mcp"
    GIT = "git"
    DOCKER = "docker"
    SHELL = "shell"
    MODEL = "model"


class FailureType(StrEnum):
    """Classification of task failures, used by the retry controller."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


class CircuitBreakerState(StrEnum):
    """States for the circuit breaker pattern."""

    CLOSED = "closed"  # Normal operation — calls pass through
    OPEN = "open"  # Failing — calls are rejected immediately
    HALF_OPEN = "half_open"  # Recovery probe — one call allowed through


class LogLevel(StrEnum):
    """Structured log entry severity."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ── Value Objects ─────────────────────────────────────────────────────────────


class TokenUsage(BaseModel):
    """Tracks LLM token consumption for an execution or single call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: TokenUsage) -> TokenUsage:
        """Return a new TokenUsage that is the sum of self and other."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=round(self.cost_usd + other.cost_usd, 8),
        )


class LogEntry(BaseModel):
    """A structured log entry attached to an execution."""

    id: UUID = Field(default_factory=uuid4)
    execution_id: UUID
    task_id: UUID | None = None
    level: LogLevel = LogLevel.INFO
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ContextSummary(BaseModel):
    """A rolling summary of execution context to reduce token overhead."""

    id: UUID = Field(default_factory=uuid4)
    execution_id: UUID
    summary: str
    token_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VerificationResult(BaseModel):
    """Structured result from the verification pipeline."""

    success: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RetryDecision(BaseModel):
    """Decision produced by the retry controller for a failed task."""

    should_retry: bool
    delay_seconds: float
    failure_type: FailureType
    reason: str


class PluginManifest(BaseModel):
    """Metadata descriptor for a Forge plugin loaded from disk."""

    name: str
    version: str
    description: str
    author: str = "Community"
    task_type: str  # must match a TaskType value
    entry_point: str = "plugin.py"


# ── Aggregate Roots ───────────────────────────────────────────────────────────


class Task(BaseModel):
    """A single executable unit within an Execution.

    Tasks are ordered by ``order_index`` and may declare ``dependencies``
    (UUIDs of tasks that must complete first).
    """

    id: UUID = Field(default_factory=uuid4)
    execution_id: UUID
    name: str
    description: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    order_index: int = 0
    dependencies: list[UUID] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3
    estimated_duration_seconds: int | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration if both timestamps are present."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class Execution(BaseModel):
    """Top-level aggregate representing a single goal-execution run.

    An Execution is created by the Planner (which populates ``tasks``),
    then driven to completion by the Orchestrator.
    """

    id: UUID = Field(default_factory=uuid4)
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    tasks: list[Task] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration if both timestamps are present."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def completed_task_count(self) -> int:
        """Count of tasks in COMPLETED status."""
        return sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)

    @property
    def failed_task_count(self) -> int:
        """Count of tasks in FAILED status."""
        return sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)
