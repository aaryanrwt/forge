"""Plugin manager benchmark."""
from __future__ import annotations

import time
from pathlib import Path
from forge.application.services.plugin_manager import PluginManager
from forge.core.config import ForgeSettings


def run_benchmark() -> float:
    """Measure plugin discovery & loading overhead.

    Returns:
        Average plugin retrieval latency in ms.
    """
    settings = ForgeSettings(plugins_dir=Path("./plugins"))
    pm = PluginManager(settings)
    
    # Warmup
    for _ in range(5):
        _ = pm.list_plugins()
        
    start = time.perf_counter()
    iterations = 500
    for _ in range(iterations):
        _ = pm.list_plugins()
    elapsed = (time.perf_counter() - start) * 1000.0
    return elapsed / iterations
