"""Integration tests validating fault injection, chaos recovery, and loop resumption."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forge.application.orchestrator import Orchestrator
from forge.core.domain.exceptions import (
    PlannerError,
)
from forge.core.domain.interfaces import (
    IMemoryRepository,
    IPlanner,
)
from forge.core.domain.models import Execution, Task, TaskStatus, TaskType


class FailingPlanner(IPlanner):
    async def plan(self, goal: str) -> Execution:
        raise PlannerError("Simulated LLM planning timeout/failure")


class MockMemoryRepository(IMemoryRepository):
    def __init__(self):
        self.executions = {}
        self.tasks = {}
        self.logs = []

    async def save_execution(self, execution: Execution) -> None:
        self.executions[execution.id] = execution

    async def get_execution(self, execution_id) -> Execution:
        return self.executions.get(execution_id)

    async def list_executions(self, limit: int = 100):
        return list(self.executions.values())[:limit]

    async def save_task(self, task: Task) -> None:
        self.tasks[task.id] = task

    async def get_task(self, task_id) -> Task:
        return self.tasks.get(task_id)

    async def get_tasks_by_execution(self, execution_id):
        return [t for t in self.tasks.values() if t.execution_id == execution_id]

    async def save_log(self, entry):
        self.logs.append(entry)

    async def get_logs_by_execution(self, execution_id):
        return [log for log in self.logs if log.execution_id == execution_id]

    async def get_logs(self, execution_id, limit: int = 100, level=None):
        res = [log for log in self.logs if log.execution_id == execution_id]
        if level:
            res = [log for log in res if log.level == level]
        return res[:limit]

    async def save_summary(self, summary):
        pass

    async def get_latest_summary(self, execution_id):
        return None

    async def get_summary(self, execution_id):
        return None

    async def get_execution_stats(self, execution_id):
        return {"total_tasks": 0, "completed_tasks": 0}

    async def init_db(self):
        pass


@pytest.mark.asyncio
async def test_fault_injection_planner_crash() -> None:
    # Set up mock dependencies
    mock_executor = AsyncMock()
    mock_verifier = AsyncMock()
    mock_retry = AsyncMock()
    mock_repo = MockMemoryRepository()
    mock_bus = AsyncMock()
    mock_opt = AsyncMock()

    orch = Orchestrator(
        planner=FailingPlanner(),
        executor_service=mock_executor,
        verifier=mock_verifier,
        retry_controller=mock_retry,
        memory_repo=mock_repo,
        event_bus=mock_bus,
        context_optimizer=mock_opt,
    )

    with pytest.raises(PlannerError):
        await orch.run("test failure")


@pytest.mark.asyncio
async def test_fault_injection_executor_exception_recovery() -> None:
    # Executor raises exception, and we verify retry loops trigger or mark task as failed
    mock_planner = AsyncMock()
    mock_planner.plan.return_value = Execution(
        id=uuid4(),
        goal="Test goal",
        tasks=[
            Task(
                id=uuid4(),
                execution_id=uuid4(),
                name="Throwing Task",
                description="",
                task_type=TaskType.SHELL,
                inputs={"command": "throw"},
            )
        ],
    )

    mock_executor = AsyncMock()
    # Mock execute raising an error
    mock_executor.execute.side_effect = Exception("Subprocess crashed (SIGKILL)")

    mock_verifier = AsyncMock()
    mock_verifier.verify.return_value.success = False
    mock_verifier.verify.return_value.message = "Failed due to subprocess crash"

    # Retry decision: do not retry
    mock_retry = AsyncMock()
    mock_decision = MagicMock()
    mock_decision.should_retry = False
    mock_decision.reason = "Unrecoverable executor error"
    mock_retry.decide.return_value = mock_decision

    mock_repo = MockMemoryRepository()
    mock_bus = AsyncMock()
    mock_opt = AsyncMock()

    orch = Orchestrator(
        planner=mock_planner,
        executor_service=mock_executor,
        verifier=mock_verifier,
        retry_controller=mock_retry,
        memory_repo=mock_repo,
        event_bus=mock_bus,
        context_optimizer=mock_opt,
    )

    # We expect run to finish with FAILED status without raising since exceptions inside tasks are handled gracefully
    res = await orch.run("Test goal")
    assert res.status == TaskStatus.FAILED
    assert len(res.tasks) == 1
    assert res.tasks[0].status == TaskStatus.FAILED
    assert "crashed" in res.tasks[0].error
