"""API router for execution endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from forge.core.container import Container
from forge.presentation.api.schemas.execution_schemas import (
    CreateExecutionRequest,
    ExecutionListResponse,
    ExecutionResponse,
)

router = APIRouter(prefix="/executions", tags=["executions"])


def _get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if not container:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Forge container not initialized",
        )
    return container


@router.post("", response_model=ExecutionResponse, status_code=status.HTTP_201_CREATED)
async def create_execution(
    payload: CreateExecutionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> ExecutionResponse:
    """Decompose a goal and launch execution in the background."""
    container = _get_container(request)

    try:
        # Create plan (runs planner.plan)
        execution = await container.planner.plan(payload.goal)
        await container.memory_repo.save_execution(execution)

        # Save each task to database
        for task in execution.tasks:
            await container.memory_repo.save_task(task)

        # Enqueue execution.orchestrator run in background
        background_tasks.add_task(container.orchestrator._run_execution, execution)

        return ExecutionResponse.from_domain(execution)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to plan and start execution: {exc}",
        ) from exc


@router.get("", response_model=ExecutionListResponse)
async def list_executions(
    request: Request,
    limit: int = 100,
) -> ExecutionListResponse:
    """Retrieve all execution runs."""
    container = _get_container(request)
    executions = await container.memory_repo.list_executions(limit=limit)
    res_list = [ExecutionResponse.from_domain(e) for e in executions]
    return ExecutionListResponse(executions=res_list, total_count=len(res_list))


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: UUID,
    request: Request,
) -> ExecutionResponse:
    """Retrieve details for a specific execution run."""
    container = _get_container(request)
    execution = await container.memory_repo.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution with ID {execution_id} not found",
        )
    return ExecutionResponse.from_domain(execution)


@router.post("/{execution_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_execution(
    execution_id: UUID,
    request: Request,
) -> dict[str, str]:
    """Request cancellation of an active execution run."""
    container = _get_container(request)
    execution = await container.memory_repo.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution with ID {execution_id} not found",
        )

    await container.orchestrator.cancel(execution_id)
    return {"message": f"Cancellation request submitted for execution {execution_id}."}


@router.post(
    "/{execution_id}/resume", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED
)
async def resume_execution(
    execution_id: UUID,
    background_tasks: BackgroundTasks,
    request: Request,
) -> ExecutionResponse:
    """Resume a failed or halted execution run from where it stopped."""
    container = _get_container(request)
    execution = await container.memory_repo.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution with ID {execution_id} not found",
        )

    # Launch resume sequence in background
    background_tasks.add_task(container.orchestrator.resume, execution_id)

    # Reload and return updated execution details
    execution_updated = await container.memory_repo.get_execution(execution_id)
    return ExecutionResponse.from_domain(execution_updated or execution)
