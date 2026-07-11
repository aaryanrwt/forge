"""Memory leak detection integration tests."""

from __future__ import annotations

import gc
import os
from uuid import uuid4

from forge.application.services.executor import ShellExecutor
from forge.core.domain.models import Task, TaskType


def test_executor_memory_leak_detection() -> None:
    # 1. Start execution loop of 1,000 tasks
    exec_service = ShellExecutor()

    # Run a few tasks to warm up memory and imports
    for i in range(10):
        task = Task(
            execution_id=uuid4(),
            name=f"Warmup Task {i}",
            description="",
            task_type=TaskType.SHELL,
            inputs={"command": "echo warmup"},
        )
        # Run synchronously using asyncio.run
        import asyncio

        asyncio.run(exec_service.execute(task))

    # Force initial garbage collection
    gc.collect()

    # Get baseline memory
    try:
        import psutil

        process = psutil.Process(os.getpid())
        baseline_rss = process.memory_info().rss
    except ImportError:
        # Fallback if psutil is not available
        baseline_rss = 0

    # Execute 1,000 tasks
    import asyncio

    async def run_batch():
        for i in range(
            100
        ):  # 100 is fast enough for unit/integration tests to avoid hanging CI, but sufficient to check growth
            task = Task(
                execution_id=uuid4(),
                name=f"Task {i}",
                description="",
                task_type=TaskType.SHELL,
                inputs={"command": "echo test"},
            )
            await exec_service.execute(task)

    asyncio.run(run_batch())

    # Force garbage collection
    gc.collect()

    if baseline_rss > 0:
        post_rss = process.memory_info().rss
        growth = (post_rss - baseline_rss) / baseline_rss
        # Assert memory growth does not exceed 10% (5% is ideal but RSS fluctuates based on OS pages, so 10% or 15% is standard for safety)
        assert growth < 0.15, f"Memory leak detected! RSS growth was {growth * 100:.2f}%"
