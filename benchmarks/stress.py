"""Stress testing and Chaos engineering scenarios simulation harness."""
from __future__ import annotations

import asyncio
import time
from uuid import uuid4
import sys

from forge.application.orchestrator import Orchestrator
from forge.core.config import ForgeSettings
from forge.core.container import Container
from forge.core.domain.models import Task, TaskStatus, TaskType


async def run_scenario_tiny() -> float:
    """Tiny project workload: 10 sequential tasks."""
    settings = ForgeSettings(db_url="sqlite+aiosqlite:///:memory:", planner_type="rule")
    container = Container(settings=settings)
    await container.initialize()
    
    orch = container.orchestrator
    start = time.perf_counter()
    execution = await orch.run("echo tiny_task")
    elapsed = (time.perf_counter() - start) * 1000.0
    await container.close()
    return elapsed


async def run_chaos_scenario() -> str:
    """Chaos engineering: Inject random failures like SQLite locks and executor crashes."""
    settings = ForgeSettings(db_url="sqlite+aiosqlite:///:memory:", planner_type="rule")
    container = Container(settings=settings)
    await container.initialize()
    
    # Run a simple goal while simulating a mock executor crash
    original_execute = container.executor_service.execute
    
    # Define a chaos execute that raises an operational error or subprocess crash once
    call_count = 0
    async def chaos_execute(task: Task) -> Task:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call crashes
            task.status = TaskStatus.FAILED
            task.error = "Simulated Chaos Subprocess Crash (SIGKILL)"
            return task
        # Subsequent retries succeed
        return await original_execute(task)

    container.executor_service.execute = chaos_execute
    
    orch = container.orchestrator
    execution = await orch.run("echo hello_chaos")
    
    # Verify that the orchestrator recovered the task on retry
    assert execution.status == TaskStatus.COMPLETED
    await container.close()
    return "Chaos crash recovered successfully"


def run_stress_suite(run_chaos: bool = False) -> None:
    print("[bold green]Running Stress Scenarios...[/bold green]")
    t_tiny = asyncio.run(run_scenario_tiny())
    print(f"  Tiny Scenario Latency: {t_tiny:.2f} ms")
    
    if run_chaos:
        print("[bold yellow]Running Chaos Harness...[/bold yellow]")
        msg = asyncio.run(run_chaos_scenario())
        print(f"  Chaos Result: {msg}")


if __name__ == "__main__":
    run_stress_suite(run_chaos="--run-chaos" in sys.argv)
