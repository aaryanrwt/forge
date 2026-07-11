"""Context compression optimizer benchmark."""

from __future__ import annotations

import asyncio
import time
from forge.application.services.context_optimizer import RollingContextOptimizer


def run_benchmark() -> float:
    """Measure context optimizer optimization time.

    Returns:
        Average optimization time in ms.
    """
    optimizer = RollingContextOptimizer(max_window_size=10)

    # 50 messages of dummy context
    context = []
    for i in range(50):
        context.append(
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"This is message number {i} with some mock text payload to compress.",
            }
        )

    # Warmup
    for _ in range(5):
        _ = asyncio.run(optimizer.optimize(context))

    start = time.perf_counter()
    iterations = 100
    for _ in range(iterations):
        _ = asyncio.run(optimizer.optimize(context))
    elapsed = (time.perf_counter() - start) * 1000.0
    return elapsed / iterations
