"""API router for task endpoints."""
from __future__ import annotations

from typing import List
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, status

from forge.core.container import Container
from forge.presentation.api.schemas.execution_schemas import TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Forge container not initialized",
        )
    return container


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    request: Request,
) -> TaskResponse:
    """Retrieve details for a specific task."""
    container = _get_container(request)
    task = await container.memory_repo.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found",
        )
    return TaskResponse(
        id=task.id,
        execution_id=task.execution_id,
        name=task.name,
        description=task.description,
        task_type=task.task_type,
        status=task.status,
        order_index=task.order_index,
        dependencies=task.dependencies,
        inputs=task.inputs,
        outputs=task.outputs,
        error=task.error,
        started_at=task.started_at,
        completed_at=task.completed_at,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        estimated_duration_seconds=task.estimated_duration_seconds,
        duration_seconds=task.duration_seconds,
    )


@router.get("/execution/{execution_id}", response_model=List[TaskResponse])
async def get_tasks_by_execution(
    execution_id: UUID,
    request: Request,
) -> List[TaskResponse]:
    """Retrieve all tasks associated with a specific execution."""
    container = _get_container(request)
    tasks = await container.memory_repo.get_tasks_by_execution(execution_id)
    return [
        TaskResponse(
            id=t.id,
            execution_id=t.execution_id,
            name=t.name,
            description=t.description,
            task_type=t.task_type,
            status=t.status,
            order_index=t.order_index,
            dependencies=t.dependencies,
            inputs=t.inputs,
            outputs=t.outputs,
            error=t.error,
            started_at=t.started_at,
            completed_at=t.completed_at,
            retry_count=t.retry_count,
            max_retries=t.max_retries,
            estimated_duration_seconds=t.estimated_duration_seconds,
            duration_seconds=t.duration_seconds,
        )
        for t in tasks
    ]
