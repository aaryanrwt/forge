"""API router for execution logs endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from forge.core.container import Container
from forge.core.domain.models import LogLevel
from forge.presentation.api.schemas.execution_schemas import LogEntryResponse

router = APIRouter(prefix="/logs", tags=["logs"])


def _get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Forge container not initialized",
        )
    return container


@router.get("/{execution_id}", response_model=list[LogEntryResponse])
async def get_logs(
    execution_id: UUID,
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    level: LogLevel | None = None,
) -> list[LogEntryResponse]:
    """Retrieve execution logs, optionally filtered by level and entry limit."""
    container = _get_container(request)
    logs = await container.memory_repo.get_logs(
        execution_id=execution_id,
        limit=limit,
        level=level,
    )
    return [
        LogEntryResponse(
            id=log.id,
            execution_id=log.execution_id,
            task_id=log.task_id,
            level=log.level,
            message=log.message,
            details=log.details,
            timestamp=log.timestamp,
        )
        for log in logs
    ]
