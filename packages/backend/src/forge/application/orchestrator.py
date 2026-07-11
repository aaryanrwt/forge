"""Forge Orchestrator — coordinates the Goal completion lifecycle loop.

Coordinates planners, executors, verifiers, and retry controllers to execute a list
of tasks sequentially. Publishes execution/task lifecycle events on the event bus.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from forge.application.services.executor import ExecutorService
from forge.application.services.memory_service import MemoryService
from forge.core.domain.events import (
    ExecutionCancelledEvent,
    ExecutionCompletedEvent,
    ExecutionCreatedEvent,
    ExecutionResumedEvent,
    ExecutionStartedEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskFailedEvent,
    TaskRetriedEvent,
    TaskStartedEvent,
    VerificationCompletedEvent,
)
from forge.core.domain.exceptions import (
    PlannerError,
)
from forge.core.domain.interfaces import (
    IContextOptimizer,
    IEventBus,
    IMemoryRepository,
    IPlanner,
    IRetryController,
    IVerifier,
)
from forge.core.domain.models import Execution, LogLevel, Task, TaskStatus, TokenUsage

logger = logging.getLogger(__name__)


class Orchestrator:
    """Core state machine that runs the Plan → Execute → Verify → Retry execution loop."""

    def __init__(
        self,
        planner: IPlanner,
        executor_service: ExecutorService,
        verifier: IVerifier,
        retry_controller: IRetryController,
        memory_repo: IMemoryRepository,
        event_bus: IEventBus,
        context_optimizer: IContextOptimizer,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.planner = planner
        self.executor_service = executor_service
        self.verifier = verifier
        self.retry_controller = retry_controller
        self.memory_repo = memory_repo
        self.event_bus = event_bus
        self.context_optimizer = context_optimizer

        # If memory_service is not injected, create a default one
        if memory_service is None:
            self.memory_service = MemoryService(memory_repo, context_optimizer)
        else:
            self.memory_service = memory_service

        self._cancelled_executions: set[UUID] = set()

    @contextmanager
    def _trace(self, execution: Execution, span_name: str):
        start = time.perf_counter()
        yield
        elapsed = (time.perf_counter() - start) * 1000.0  # ms
        self._record_span(execution, span_name, elapsed)

    def _record_span(self, execution: Execution, span_name: str, duration_ms: float) -> None:
        if "telemetry" not in execution.metadata:
            execution.metadata["telemetry"] = {"spans": [], "metrics": {}}

        telemetry = execution.metadata["telemetry"]
        telemetry["spans"].append(
            {
                "span": span_name,
                "duration_ms": duration_ms,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        metrics = telemetry["metrics"]
        metrics[f"{span_name.lower()}_ms"] = (
            metrics.get(f"{span_name.lower()}_ms", 0.0) + duration_ms
        )

    async def run(self, goal: str) -> Execution:
        """Decompose a natural-language goal and execute the resulting plan.

        Args:
            goal: Natural language prompt or instruction.
        """
        logger.info("Starting orchestrator run for goal: %r", goal)

        # 1. Plan
        start_plan = time.perf_counter()
        try:
            execution = await self.planner.plan(goal)
        except Exception as exc:
            logger.exception("Goal planning failed")
            raise PlannerError(f"Goal planning failed: {exc}") from exc
        elapsed_plan = (time.perf_counter() - start_plan) * 1000.0
        self._record_span(execution, "Planner", elapsed_plan)

        # 2. Persist execution and publish event
        with self._trace(execution, "Memory"):
            await self.memory_repo.save_execution(execution)
            await self.event_bus.publish(ExecutionCreatedEvent(execution=execution))

            for task in execution.tasks:
                await self.memory_repo.save_task(task)
                await self.event_bus.publish(TaskCreatedEvent(task=task))

        # 3. Start loop
        execution.status = TaskStatus.IN_PROGRESS
        execution.started_at = datetime.utcnow()
        with self._trace(execution, "Memory"):
            await self.memory_repo.save_execution(execution)
        await self.event_bus.publish(ExecutionStartedEvent(execution_id=execution.id))

        await self.memory_service.log(
            execution.id,
            f"Execution started. Decomposed into {len(execution.tasks)} tasks.",
        )

        return await self._run_execution(execution)

    async def resume(self, execution_id: UUID) -> Execution:
        """Resume an existing, halted/failed execution.

        Skips already completed tasks and runs the remaining tasks.
        """
        logger.info("Resuming execution: %s", execution_id)
        execution = await self.memory_repo.get_execution(execution_id)
        if not execution:
            raise PlannerError(f"Execution {execution_id} not found to resume")

        if execution.status == TaskStatus.COMPLETED:
            logger.info("Execution %s is already completed", execution_id)
            return execution

        # Find the index of the first incomplete task
        first_incomplete_idx = 0
        for task in execution.tasks:
            if task.status != TaskStatus.COMPLETED:
                first_incomplete_idx = task.order_index
                break

        execution.status = TaskStatus.IN_PROGRESS
        execution.completed_at = None
        execution.error = None
        await self.memory_repo.save_execution(execution)

        await self.event_bus.publish(
            ExecutionResumedEvent(
                execution_id=execution_id,
                from_task_index=first_incomplete_idx,
            )
        )
        await self.memory_service.log(
            execution.id,
            f"Resumed execution from task index {first_incomplete_idx}.",
        )

        # Clear loop detector history for clean retry tracking on resume
        if hasattr(self.retry_controller, "loop_detector"):
            self.retry_controller.loop_detector.clear(execution_id)

        # If it was cancelled previously, make sure it is uncancelled
        self._cancelled_executions.discard(execution_id)

        return await self._run_execution(execution)

    async def cancel(self, execution_id: UUID) -> None:
        """Register a cancellation request for a running execution."""
        logger.info("Cancellation requested for execution: %s", execution_id)
        self._cancelled_executions.add(execution_id)

    async def _run_execution(self, execution: Execution) -> Execution:
        """Internal execution loop running tasks sequentially."""
        exec_id = execution.id

        try:
            # Re-sort tasks by order index to ensure correct sequence
            sorted_tasks = sorted(execution.tasks, key=lambda t: t.order_index)

            for task in sorted_tasks:
                # Check cancellation flag before launching task
                if exec_id in self._cancelled_executions:
                    logger.info("Execution %s cancelled mid-run", exec_id)
                    execution.status = TaskStatus.CANCELLED
                    execution.error = "Execution cancelled by user request"
                    await self.event_bus.publish(
                        ExecutionCancelledEvent(execution_id=exec_id, reason=execution.error)
                    )
                    break

                if task.status == TaskStatus.COMPLETED:
                    logger.debug("Skipping already completed task: %s", task.name)
                    continue

                # Run the task execution lifecycle (Execute -> Verify -> Retry)
                logger.info("Running task: %s (%s)", task.name, task.task_type.value)
                await self._execute_task(task, execution)

                # Check cancellation flag again after task execution
                if exec_id in self._cancelled_executions:
                    logger.info("Execution %s cancelled mid-run", exec_id)
                    execution.status = TaskStatus.CANCELLED
                    execution.error = "Execution cancelled by user request"
                    await self.event_bus.publish(
                        ExecutionCancelledEvent(execution_id=exec_id, reason=execution.error)
                    )
                    break

                # Re-fetch task to check if it failed permanently
                task_refreshed = await self.memory_repo.get_task(task.id)
                if task_refreshed and task_refreshed.status == TaskStatus.FAILED:
                    execution.status = TaskStatus.FAILED
                    execution.error = task_refreshed.error
                    break

            else:
                # All tasks completed successfully
                if execution.status == TaskStatus.IN_PROGRESS:
                    execution.status = TaskStatus.COMPLETED
                    await self.memory_service.log(
                        execution.id,
                        "All tasks completed successfully. Goal completed.",
                    )

        except Exception as exc:
            logger.exception("Exception in execution loop")
            execution.status = TaskStatus.FAILED
            execution.error = str(exc)
            await self.memory_service.log(
                execution.id,
                f"Execution failed with exception: {exc}",
                level=LogLevel.ERROR,
            )

        execution.completed_at = datetime.utcnow()
        await self.memory_repo.save_execution(execution)

        # Publish overall execution completion event
        success = execution.status == TaskStatus.COMPLETED
        total_tokens = execution.token_usage.total_tokens
        await self.event_bus.publish(
            ExecutionCompletedEvent(
                execution_id=exec_id,
                success=success,
                token_usage=total_tokens,
                error=execution.error,
            )
        )

        return execution

    async def _execute_task(self, task: Task, execution: Execution) -> None:
        """Run the Execute → Verify → (Conditional Retry) loop for a single Task."""
        exec_id = execution.id

        await self.event_bus.publish(TaskStartedEvent(task_id=task.id, execution_id=exec_id))
        await self.memory_service.log(
            exec_id,
            f"Starting task '{task.name}' ({task.task_type.value})",
            task_id=task.id,
        )

        while True:
            # 1. Run Executor
            task.started_at = datetime.utcnow()
            task.status = TaskStatus.IN_PROGRESS
            with self._trace(execution, "Memory"):
                await self.memory_repo.save_task(task)

            # Delegate to executor service
            start_exec = time.perf_counter()
            try:
                task = await self.executor_service.execute(task)
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.error = f"Executor raised exception: {exc}"
                task.completed_at = datetime.utcnow()
            elapsed_exec = (time.perf_counter() - start_exec) * 1000.0
            self._record_span(execution, "Executor", elapsed_exec)

            # Check if this task was executed by a plugin
            is_plugin = False
            if hasattr(self.executor_service, "_executors"):
                for executor in self.executor_service._executors:
                    if executor.supports(task.task_type):
                        if "Plugin" in executor.__class__.__name__:
                            is_plugin = True
                        break
            if is_plugin:
                self._record_span(execution, "Plugin", elapsed_exec)

            # Keep track of token usage if this was a model/LLM task
            if task.outputs and "token_usage" in task.outputs:
                try:
                    usage_dict = task.outputs["token_usage"]
                    tu = TokenUsage(**usage_dict)
                    execution.token_usage = execution.token_usage.add(tu)
                    with self._trace(execution, "Memory"):
                        await self.memory_repo.save_execution(execution)
                except Exception:
                    pass

            with self._trace(execution, "Memory"):
                await self.memory_repo.save_task(task)

            # 2. Run Verification
            with self._trace(execution, "Verifier"):
                verification = await self.verifier.verify(task)
            await self.event_bus.publish(
                VerificationCompletedEvent(
                    task_id=task.id,
                    execution_id=exec_id,
                    success=verification.success,
                    details=verification.details,
                )
            )

            if verification.success:
                # Task succeeded
                task.status = TaskStatus.COMPLETED
                task.error = None
                task.completed_at = datetime.utcnow()
                with self._trace(execution, "Memory"):
                    await self.memory_repo.save_task(task)

                # Reset circuit breaker on success
                if hasattr(self.retry_controller, "record_success"):
                    self.retry_controller.record_success(task)

                await self.event_bus.publish(
                    TaskCompletedEvent(
                        task_id=task.id,
                        execution_id=exec_id,
                        success=True,
                        outputs=task.outputs,
                    )
                )
                await self.memory_service.log(
                    exec_id,
                    f"Task '{task.name}' completed successfully: {verification.message}",
                    task_id=task.id,
                    details=verification.details,
                )
                break

            # 3. Task Failed (Verification failure)
            # Fetch error message
            error_msg = task.error or verification.message or "Verification failed"
            task.error = error_msg
            task.status = TaskStatus.FAILED
            with self._trace(execution, "Memory"):
                await self.memory_repo.save_task(task)

            # Ask RetryController for decision
            with self._trace(execution, "Retry"):
                retry_decision = await self.retry_controller.decide(task, error_msg)
            await self.event_bus.publish(
                TaskFailedEvent(
                    task_id=task.id,
                    execution_id=exec_id,
                    error=error_msg,
                    retry_decision=retry_decision,
                )
            )

            if retry_decision.should_retry:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                with self._trace(execution, "Memory"):
                    await self.memory_repo.save_task(task)

                await self.memory_service.log(
                    exec_id,
                    f"Task '{task.name}' failed: {error_msg}. Retrying in {retry_decision.delay_seconds:.1f}s (Attempt {task.retry_count}/{task.max_retries})",
                    task_id=task.id,
                    details={"retry_decision": retry_decision.model_dump()},
                )

                await self.event_bus.publish(
                    TaskRetriedEvent(
                        task_id=task.id,
                        execution_id=exec_id,
                        retry_count=task.retry_count,
                        delay_seconds=retry_decision.delay_seconds,
                    )
                )

                # Sleep before retrying
                await asyncio.sleep(retry_decision.delay_seconds)
            else:
                # Permanent failure or out of retries
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.utcnow()
                with self._trace(execution, "Memory"):
                    await self.memory_repo.save_task(task)

                await self.memory_service.log(
                    exec_id,
                    f"Task '{task.name}' failed permanently: {error_msg}. Reason: {retry_decision.reason}",
                    task_id=task.id,
                    level=LogLevel.ERROR,
                )
                break
