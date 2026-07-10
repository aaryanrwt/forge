"""Integration tests for SQLite memory repository CRUD."""
from __future__ import annotations

from uuid import uuid4
import pytest

from forge.core.container import Container
from forge.core.domain.models import ContextSummary, Execution, LogEntry, LogLevel, Task, TaskStatus, TaskType


@pytest.mark.asyncio
async def test_execution_and_task_lifecycle(test_container: Container) -> None:
    repo = test_container.memory_repo

    exec_id = uuid4()
    execution = Execution(id=exec_id, goal="Build tests", status=TaskStatus.PENDING)
    
    # 1. Save and fetch execution
    await repo.save_execution(execution)
    fetched_exec = await repo.get_execution(exec_id)
    assert fetched_exec is not None
    assert fetched_exec.goal == "Build tests"
    assert fetched_exec.status == TaskStatus.PENDING

    # 2. Add tasks and verify retrieval
    task1 = Task(execution_id=exec_id, name="Run setup", description="", task_type=TaskType.SHELL, status=TaskStatus.PENDING)
    task2 = Task(execution_id=exec_id, name="Run tests", description="", task_type=TaskType.PYTHON, status=TaskStatus.PENDING, order_index=1)
    
    await repo.save_task(task1)
    await repo.save_task(task2)

    tasks = await repo.get_tasks_by_execution(exec_id)
    assert len(tasks) == 2
    assert tasks[0].name == "Run setup"
    assert tasks[1].name == "Run tests"

    # 3. List executions
    all_execs = await repo.list_executions()
    assert len(all_execs) >= 1
    assert any(e.id == exec_id for e in all_execs)


@pytest.mark.asyncio
async def test_logs_and_summaries_persistence(test_container: Container) -> None:
    repo = test_container.memory_repo
    exec_id = uuid4()
    
    # Pre-requisite: save execution first due to foreign key constraints
    execution = Execution(id=exec_id, goal="Test logging", status=TaskStatus.IN_PROGRESS)
    await repo.save_execution(execution)

    # 1. Save logs and verify retrieval
    log1 = LogEntry(execution_id=exec_id, level=LogLevel.INFO, message="Starting task")
    log2 = LogEntry(execution_id=exec_id, level=LogLevel.WARNING, message="Warning raised")
    
    await repo.save_log(log1)
    await repo.save_log(log2)

    fetched_logs = await repo.get_logs(exec_id)
    assert len(fetched_logs) == 2
    messages = [log.message for log in fetched_logs]
    assert "Starting task" in messages
    assert "Warning raised" in messages
    levels = [log.level for log in fetched_logs]
    assert LogLevel.INFO in levels
    assert LogLevel.WARNING in levels

    # Filter logs by level
    warn_logs = await repo.get_logs(exec_id, level=LogLevel.WARNING)
    assert len(warn_logs) == 1
    assert warn_logs[0].message == "Warning raised"

    # 2. Save summary
    summary = ContextSummary(execution_id=exec_id, summary="Completed 0/0 tasks", token_count=4)
    await repo.save_summary(summary)
    
    fetched_summary = await repo.get_summary(exec_id)
    assert fetched_summary is not None
    assert fetched_summary.summary == "Completed 0/0 tasks"
