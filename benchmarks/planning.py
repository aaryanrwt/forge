"""Planning overhead benchmark."""
from __future__ import annotations

import asyncio
import time
from forge.application.services.planner import RulePlanner


def run_benchmark() -> float:
    """Measure RulePlanner planning decomposition latency (excluding LLM calls).

    Returns:
        Average planning latency in ms.
    """
    planner = RulePlanner()
    goal = "Create a new python CLI tool that formats JSON. Run tests using pytest. If they fail, fix them."
    
    # Warmup
    for _ in range(5):
        _ = asyncio.run(planner.plan(goal))
        
    start = time.perf_counter()
    iterations = 50
    for _ in range(iterations):
        _ = asyncio.run(planner.plan(goal))
    elapsed = (time.perf_counter() - start) * 1000.0
    return elapsed / iterations
