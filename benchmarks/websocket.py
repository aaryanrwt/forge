"""WebSocket messaging latency benchmark."""
from __future__ import annotations

import asyncio
import time
from uuid import uuid4
from fastapi.testclient import TestClient
from forge.presentation.api.main import app
from forge.core.config import ForgeSettings
from forge.core.container import Container


def run_benchmark() -> float:
    """Measure WebSocket connection overhead.

    Returns:
        Average connection creation latency in ms.
    """
    settings = ForgeSettings(
        db_url="sqlite+aiosqlite:///:memory:",
    )
    container = Container(settings=settings)
    asyncio.run(container.initialize())
    app.state.container = container
    
    client = TestClient(app)
    exec_id = uuid4()
    
    # Warmup
    for _ in range(3):
        with client.websocket_connect(f"/ws/executions/{exec_id}"):
            pass
            
    start = time.perf_counter()
    iterations = 20
    for _ in range(iterations):
        with client.websocket_connect(f"/ws/executions/{exec_id}"):
            pass
    elapsed = (time.perf_counter() - start) * 1000.0
    
    asyncio.run(container.close())
    return elapsed / iterations
