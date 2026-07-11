"""Integration tests for the Orchestrator loop."""

from __future__ import annotations

import asyncio

import pytest

from forge.core.container import Container
from forge.core.domain.models import TaskStatus, TaskType


@pytest.mark.asyncio
async def test_orchestrator_complete_execution_loop(test_container: Container) -> None:
    # We will run a simple shell command that succeeds
    goal = "echo success"

    # Run orchestrator
    execution = await test_container.orchestrator.run(goal)

    assert execution.status == TaskStatus.COMPLETED
    assert len(execution.tasks) == 1

    task = execution.tasks[0]
    assert task.task_type == TaskType.SHELL
    assert task.status == TaskStatus.COMPLETED

    # Verify outputs are populated
    assert task.outputs["returncode"] == 0
    assert "success" in task.outputs["stdout"].lower()

    # Verify logs were saved
    logs = await test_container.memory_repo.get_logs(execution.id)
    assert len(logs) > 0
    assert any("Execution started" in log.message for log in logs)
    assert any("completed successfully" in log.message for log in logs)


@pytest.mark.asyncio
async def test_orchestrator_cancellation_flow(test_container: Container) -> None:
    # A long-running command that we can cancel
    goal = "ping 127.0.0.1 -n 6 > nul"

    # We will start the run in the background, sleep briefly, then cancel
    run_task = asyncio.create_task(test_container.orchestrator.run(goal))

    await asyncio.sleep(0.1)

    # Fetch execution ID from running tasks or planner output
    # Let's inspect the active executions in repo
    execs = await test_container.memory_repo.list_executions()
    assert len(execs) > 0
    exec_id = execs[0].id

    # Cancel execution
    await test_container.orchestrator.cancel(exec_id)

    # Await completion
    final_execution = await run_task

    assert final_execution.status == TaskStatus.CANCELLED
    assert "cancelled" in final_execution.error.lower()
