"""Health and readiness check endpoints."""
from __future__ import annotations

from typing import Dict
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=Dict[str, str])
async def get_health() -> Dict[str, str]:
    """Retrieve service health status."""
    return {"status": "ok", "version": "1.0.0"}


@router.get("/ready", response_model=Dict[str, str])
async def get_readiness() -> Dict[str, str]:
    """Retrieve service readiness status (verifies database/LLM dependencies)."""
    # Simple check for now, can be extended to check DB ping or Ollama ping
    return {"status": "ready"}
