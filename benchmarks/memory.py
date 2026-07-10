"""SQLite database persistence read/write benchmark."""
from __future__ import annotations

import asyncio
import time
from uuid import uuid4
from forge.core.config import ForgeSettings
from forge.core.container import Container
from forge.core.domain.models import Execution, TaskStatus


def run_benchmark() -> float:
    """Measure SQLite read/write latency for storing execution state.

    Returns:
        Average DB write/read time in ms.
    """
    settings = ForgeSettings(
        db_url="sqlite+aiosqlite:///:memory:",
    )
    
    async def _run():
        container = Container(settings=settings)
        await container.initialize()
        
        # Warmup
        for _ in range(5):
            exec_id = uuid4()
            ex = Execution(id=exec_id, goal="benchmark goal", status=TaskStatus.PENDING)
            await container.memory_repo.save_execution(ex)
            _ = await container.memory_repo.get_execution(exec_id)
            
        start = time.perf_counter()
        iterations = 50
        for _ in range(iterations):
            exec_id = uuid4()
            ex = Execution(id=exec_id, goal="benchmark goal", status=TaskStatus.PENDING)
            await container.memory_repo.save_execution(ex)
            _ = await container.memory_repo.get_execution(exec_id)
            
        elapsed = (time.perf_counter() - start) * 1000.0
        await container.close()
        return elapsed / iterations

    return asyncio.run(_run())
