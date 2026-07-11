"""Verifier latency benchmark."""

from __future__ import annotations

import time
from uuid import uuid4
from forge.application.services.verifier import (
    CompositeVerifier,
    ExitCodeVerifier,
    OutputPatternVerifier,
    TaskStatusVerifier,
)
from forge.core.domain.models import Task, TaskStatus, TaskType


def run_benchmark() -> float:
    """Measure assertion validation latency.

    Returns:
        Average verification time in ms.
    """
    verifier = CompositeVerifier(
        [
            TaskStatusVerifier(),
            ExitCodeVerifier(),
            OutputPatternVerifier(),
        ]
    )

    task = Task(
        execution_id=uuid4(),
        name="verify task",
        description="",
        task_type=TaskType.SHELL,
        inputs={"command": "echo verify"},
        outputs={"returncode": 0, "stdout": "Success message"},
        status=TaskStatus.COMPLETED,
    )

    # Warmup
    import asyncio

    for _ in range(5):
        _ = asyncio.run(verifier.verify(task))

    start = time.perf_counter()
    iterations = 200
    for _ in range(iterations):
        _ = asyncio.run(verifier.verify(task))
    elapsed = (time.perf_counter() - start) * 1000.0
    return elapsed / iterations
