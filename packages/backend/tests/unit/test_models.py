"""Unit tests for domain models."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
import pytest

from forge.core.domain.models import Execution, Task, TaskStatus, TaskType, TokenUsage


def test_token_usage_addition() -> None:
    t1 = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, cost_usd=0.01)
    t2 = TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300, cost_usd=0.02)
    
    t3 = t1.add(t2)
    assert t3.prompt_tokens == 300
    assert t3.completion_tokens == 150
    assert t3.total_tokens == 450
    assert t3.cost_usd == pytest.approx(0.03)


def test_task_duration_calculation() -> None:
    now = datetime.utcnow()
    task = Task(
        execution_id=uuid4(),
        name="Test",
        description="test task",
        task_type=TaskType.SHELL,
        started_at=now,
        completed_at=now + timedelta(seconds=12.5),
    )
    assert task.duration_seconds == pytest.approx(12.5)


def test_execution_completed_and_failed_counts() -> None:
    exec_id = uuid4()
    tasks = [
        Task(execution_id=exec_id, name="t1", description="", task_type=TaskType.SHELL, status=TaskStatus.COMPLETED),
        Task(execution_id=exec_id, name="t2", description="", task_type=TaskType.PYTHON, status=TaskStatus.FAILED),
        Task(execution_id=exec_id, name="t3", description="", task_type=TaskType.GIT, status=TaskStatus.PENDING),
    ]
    execution = Execution(goal="Run tests", tasks=tasks)
    
    assert execution.completed_task_count == 1
    assert execution.failed_task_count == 1
