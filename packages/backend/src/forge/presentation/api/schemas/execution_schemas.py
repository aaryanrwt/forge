"""Pydantic schemas for executions, tasks, and logs endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from forge.core.domain.models import LogLevel, TaskStatus, TaskType


class CreateExecutionRequest(BaseModel):
    """Payload to start or plan a new goal execution."""

    goal: str = Field(..., description="The natural language goal/instruction to run.")


class TaskResponse(BaseModel):
    """API representation of a Task."""

    id: UUID
    execution_id: UUID
    name: str
    description: str
    task_type: TaskType
    status: TaskStatus
    order_index: int
    dependencies: list[UUID]
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int
    max_retries: int
    estimated_duration_seconds: int | None = None
    duration_seconds: float | None = None


class ExecutionResponse(BaseModel):
    """API representation of an Execution, including its tasks."""

    id: UUID
    goal: str
    status: TaskStatus
    tasks: list[TaskResponse]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    token_usage_prompt_tokens: int = Field(0, alias="prompt_tokens")
    token_usage_completion_tokens: int = Field(0, alias="completion_tokens")
    token_usage_total_tokens: int = Field(0, alias="total_tokens")
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float | None = None
    completed_task_count: int
    failed_task_count: int

    model_config = {
        "populate_by_name": True,
    }

    @classmethod
    def from_domain(cls, execution: Any) -> ExecutionResponse:
        """Helper to convert domain model to schema."""
        tasks = [
            TaskResponse(
                id=t.id,
                execution_id=t.execution_id,
                name=t.name,
                description=t.description,
                task_type=t.task_type,
                status=t.status,
                order_index=t.order_index,
                dependencies=t.dependencies,
                inputs=t.inputs,
                outputs=t.outputs,
                error=t.error,
                started_at=t.started_at,
                completed_at=t.completed_at,
                retry_count=t.retry_count,
                max_retries=t.max_retries,
                estimated_duration_seconds=t.estimated_duration_seconds,
                duration_seconds=t.duration_seconds,
            )
            for t in execution.tasks
        ]
        return cls(
            id=execution.id,
            goal=execution.goal,
            status=execution.status,
            tasks=tasks,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            prompt_tokens=execution.token_usage.prompt_tokens,
            completion_tokens=execution.token_usage.completion_tokens,
            total_tokens=execution.token_usage.total_tokens,
            error=execution.error,
            metadata=execution.metadata,
            duration_seconds=execution.duration_seconds,
            completed_task_count=execution.completed_task_count,
            failed_task_count=execution.failed_task_count,
        )


class ExecutionListResponse(BaseModel):
    """Paginated or limited list of executions."""

    executions: list[ExecutionResponse]
    total_count: int


class LogEntryResponse(BaseModel):
    """API representation of a structured execution log entry."""

    id: UUID
    execution_id: UUID
    task_id: UUID | None = None
    level: LogLevel
    message: str
    details: dict[str, Any]
    timestamp: datetime
