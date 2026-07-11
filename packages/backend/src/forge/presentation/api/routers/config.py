"""API router for config/settings management endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from forge.core.container import Container
from forge.presentation.api.schemas.config_schemas import ConfigResponse

router = APIRouter(prefix="/config", tags=["config"])


def _get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Forge container not initialized",
        )
    return container


@router.get("", response_model=ConfigResponse)
async def get_config(request: Request) -> ConfigResponse:
    """Retrieve the current running server configuration parameters."""
    container = _get_container(request)
    settings = container.settings
    return ConfigResponse(
        db_url=settings.db_url,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        planner_type=settings.planner_type,
        executor_timeout=settings.executor_timeout,
        default_max_retries=settings.default_max_retries,
        circuit_breaker_threshold=settings.circuit_breaker_threshold,
        circuit_breaker_timeout=settings.circuit_breaker_timeout,
        context_window_size=settings.context_window_size,
        plugins_dir=str(settings.plugins_dir),
        log_level=settings.log_level,
    )
