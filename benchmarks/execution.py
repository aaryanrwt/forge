"""Execution loop dispatcher overhead benchmark."""
from __future__ import annotations

import asyncio
import time
from uuid import uuid4
from forge.application.services.executor import ExecutorService, ShellExecutor
from forge.core.domain.models import Task, TaskStatus, TaskType


def run_benchmark() -> float:
    """Measure sequential execution dispatcher and resolution overhead.

    Returns:
        Average execution lookup & mapping latency in ms.
    """
    shell_executor = ShellExecutor()
    # Mock execute to make it an instant return
    async def instant_exec(task: Task) -> Task:
        task.status = TaskStatus.COMPLETED
        return task
    shell_executor.execute = instant_exec

    service = ExecutorService([shell_executor])
    task = Task(
        execution_id=uuid4(),
        name="bench task",
        description="",
        task_type=TaskType.SHELL,
        inputs={"command": "echo bench"},
    )
    
    # Warmup
    for _ in range(5):
        _ = asyncio.run(service.execute(task))
        
    start = time.perf_counter()
    iterations = 500
    for _ in range(iterations):
        _ = asyncio.run(service.execute(task))
    elapsed = (time.perf_counter() - start) * 1000.0
    return elapsed / iterations
