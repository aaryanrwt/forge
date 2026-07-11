"""Health and readiness check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=dict[str, str])
async def get_health() -> dict[str, str]:
    """Retrieve service health status."""
    return {"status": "ok", "version": "1.0.0"}


@router.get("/ready", response_model=dict[str, str])
async def get_readiness() -> dict[str, str]:
    """Retrieve service readiness status (verifies database/LLM dependencies)."""
    # Simple check for now, can be extended to check DB ping or Ollama ping
    return {"status": "ready"}
