"""Forge Memory Service — high-level facade for state persistence and context retrieval.

Wires together the persistent memory repository and context optimizer to build
context windows for LLMs and fetch logs/summaries/statistics.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from forge.core.domain.interfaces import IContextOptimizer, IMemoryRepository
from forge.core.domain.models import (
    ContextSummary,
    Execution,
    LogEntry,
    LogLevel,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class MemoryService:
    """Facade service for managing execution logs, summaries, and conversation context.

    Saves log entries and constructs optimized prompt context arrays for the LLM
    by extracting execution and task history from the DB and filtering/truncating it.
    """

    def __init__(
        self,
        repository: IMemoryRepository,
        optimizer: IContextOptimizer,
    ) -> None:
        """Initialize the MemoryService.

        Args:
            repository: Underlying memory repository for SQLite CRUD operations.
            optimizer: Context optimizer to prune/truncate the retrieved message histories.
        """
        self.repository = repository
        self.optimizer = optimizer

    async def log(
        self,
        execution_id: UUID,
        message: str,
        level: LogLevel = LogLevel.INFO,
        task_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> LogEntry:
        """Create, persist, and return a new structured LogEntry.

        Args:
            execution_id: ID of the parent execution run.
            message: Plain-text log message.
            level: Log level (DEBUG, INFO, WARNING, ERROR).
            task_id: Optional UUID of the task this log is associated with.
            details: Optional dict of structured metadata keys/values.
        """
        entry = LogEntry(
            execution_id=execution_id,
            task_id=task_id,
            level=level,
            message=message,
            details=details or {},
        )
        await self.repository.save_log(entry)
        logger.debug("[%s] Log saved: %s", level.value.upper(), message)
        return entry

    async def get_execution_context(self, execution_id: UUID) -> List[Dict[str, Any]]:
        """Build and optimize a history-based context array for an execution.

        Aggregates the goal description, past completed tasks (with their inputs/outputs),
        and any failed tasks or errors, constructing a conversation-like context list
        which is then compressed using the context optimizer.
        """
        execution = await self.repository.get_execution(execution_id)
        if not execution:
            logger.warning("Could not find execution %s to build context", execution_id)
            return []

        # Start with the main goal
        context: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"You are Forge, executing the goal: '{execution.goal}'.\n"
                    "Your execution context contains a list of tasks that have been "
                    "processed so far, including their inputs and outputs/results."
                ),
            }
        ]

        # Fetch all tasks in chronological order
        tasks = await self.repository.get_tasks_by_execution(execution_id)
        for t in tasks:
            if t.status == TaskStatus.COMPLETED:
                context.append(
                    {
                        "role": "user",
                        "content": (
                            f"Task Completed: '{t.name}' (Type: {t.task_type.value})\n"
                            f"Inputs: {t.inputs}\n"
                            f"Outputs: {t.outputs}"
                        ),
                    }
                )
            elif t.status == TaskStatus.FAILED:
                context.append(
                    {
                        "role": "user",
                        "content": (
                            f"Task Failed: '{t.name}' (Type: {t.task_type.value})\n"
                            f"Inputs: {t.inputs}\n"
                            f"Error: {t.error}\n"
                            f"Retry Count: {t.retry_count}/{t.max_retries}"
                        ),
                    }
                )

        # Optimize the compiled context
        start_opt = time.perf_counter()
        optimized_context = await self.optimizer.optimize(context)
        elapsed_opt = (time.perf_counter() - start_opt) * 1000.0

        if "telemetry" not in execution.metadata:
            execution.metadata["telemetry"] = {"spans": [], "metrics": {}}
        telemetry = execution.metadata["telemetry"]
        telemetry["spans"].append({
            "span": "Optimizer",
            "duration_ms": elapsed_opt,
            "timestamp": datetime.utcnow().isoformat()
        })
        metrics = telemetry["metrics"]
        metrics["optimizer_ms"] = metrics.get("optimizer_ms", 0.0) + elapsed_opt
        
        # Save updated execution metadata containing optimizer trace
        await self.repository.save_execution(execution)
        return optimized_context

    async def summarize_execution(self, execution_id: UUID) -> str:
        """Generate and save a plain English summary of what has happened so far.

        Args:
            execution_id: ID of the execution.

        Returns:
            A string summary.
        """
        execution = await self.repository.get_execution(execution_id)
        if not execution:
            return "Execution not found."

        tasks = execution.tasks
        total_tasks = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        pending = sum(
            1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        )

        summary_lines = [
            f"Execution Summary for goal: '{execution.goal}'",
            f"Current Status: {execution.status.value.upper()}",
            f"Task Progress: {completed}/{total_tasks} completed, {failed} failed, {pending} pending.",
        ]

        if tasks:
            summary_lines.append("\nTasks:")
            for t in tasks:
                status_char = "✓" if t.status == TaskStatus.COMPLETED else "✗" if t.status == TaskStatus.FAILED else "•"
                summary_lines.append(f"  [{status_char}] {t.name} ({t.task_type.value}) -> {t.status.value}")

        summary_text = "\n".join(summary_lines)

        # Save the summary to the DB
        summary = ContextSummary(
            execution_id=execution_id,
            summary=summary_text,
            token_count=len(summary_text) // 4,
        )
        await self.repository.save_summary(summary)

        return summary_text
