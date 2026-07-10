"""API endpoint overhead benchmark."""
from __future__ import annotations

import asyncio
import time
from fastapi.testclient import TestClient
from forge.presentation.api.main import app
from forge.core.config import ForgeSettings
from forge.core.container import Container


def run_benchmark() -> float:
    """Measure API routing and parsing overhead (excluding database/planner loops).

    Returns:
        Average request latency in ms.
    """
    settings = ForgeSettings(
        db_url="sqlite+aiosqlite:///:memory:",
    )
    container = Container(settings=settings)
    asyncio.run(container.initialize())
    app.state.container = container
    
    client = TestClient(app)
    
    # Warmup
    for _ in range(5):
        _ = client.get("/health")
        
    start = time.perf_counter()
    iterations = 100
    for _ in range(iterations):
        _ = client.get("/health")
    elapsed = (time.perf_counter() - start) * 1000.0
    
    asyncio.run(container.close())
    return elapsed / iterations
