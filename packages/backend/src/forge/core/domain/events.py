"""Forge domain events — published over the event bus.

All events are immutable Pydantic models derived from BaseEvent.  They are
published by the Orchestrator and consumed by any subscriber (logging,
WebSocket push, metrics, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from forge.core.domain.models import Execution, Task


class BaseEvent(BaseModel):
    """All Forge events inherit from this base."""

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Execution Events ──────────────────────────────────────────────────────────


class ExecutionCreatedEvent(BaseEvent):
    """Fired immediately after the planner creates a new Execution."""

    execution: Execution


class ExecutionStartedEvent(BaseEvent):
    """Fired when the orchestrator begins processing an Execution."""

    execution_id: UUID


class ExecutionCompletedEvent(BaseEvent):
    """Fired when an Execution finishes (success or failure)."""

    execution_id: UUID
    success: bool
    token_usage: int = 0
    error: str | None = None


class ExecutionCancelledEvent(BaseEvent):
    """Fired when an Execution is explicitly cancelled."""

    execution_id: UUID
    reason: str = "User requested cancellation"


class ExecutionResumedEvent(BaseEvent):
    """Fired when a previously stopped Execution is resumed."""

    execution_id: UUID
    from_task_index: int = 0


# ── Task Events ───────────────────────────────────────────────────────────────


class TaskCreatedEvent(BaseEvent):
    """Fired when a new Task is registered in the repository."""

    task: Task


class TaskStartedEvent(BaseEvent):
    """Fired immediately before an executor begins running a Task."""

    task_id: UUID
    execution_id: UUID


class TaskCompletedEvent(BaseEvent):
    """Fired when a Task finishes successfully."""

    task_id: UUID
    execution_id: UUID
    success: bool
    outputs: dict[str, Any] = Field(default_factory=dict)


class TaskFailedEvent(BaseEvent):
    """Fired when a Task fails (before retry decision)."""

    task_id: UUID
    execution_id: UUID
    error: str
    retry_decision: Any | None = None


class TaskRetriedEvent(BaseEvent):
    """Fired when a Task is scheduled for another execution attempt."""

    task_id: UUID
    execution_id: UUID
    retry_count: int
    delay_seconds: float = 0.0


# ── Verification Events ───────────────────────────────────────────────────────


class VerificationCompletedEvent(BaseEvent):
    """Fired after the verifier has inspected a Task result."""

    task_id: UUID
    execution_id: UUID
    success: bool
    details: dict[str, Any] = Field(default_factory=dict)


# ── System Events ─────────────────────────────────────────────────────────────


class ContextOptimizedEvent(BaseEvent):
    """Fired after the context optimizer compresses a context window."""

    execution_id: UUID
    tokens_saved: int
    original_size: int
    optimized_size: int


class CircuitBreakerOpenedEvent(BaseEvent):
    """Fired when an executor's circuit breaker transitions to OPEN."""

    executor_name: str
    failure_count: int


class LogEntryEvent(BaseEvent):
    """Lightweight event for real-time log streaming."""

    execution_id: UUID
    message: str
    level: str = "info"


class PluginLoadedEvent(BaseEvent):
    """Fired when the PluginManager successfully loads a plugin."""

    plugin_name: str
    plugin_version: str
