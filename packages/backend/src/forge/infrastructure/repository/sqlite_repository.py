"""SQLite-backed implementation of IMemoryRepository.

Uses SQLAlchemy 2.0 async engine + aiosqlite driver.  All domain ↔ ORM
conversions happen here; the domain layer remains infrastructure-free.

Implements the full IMemoryRepository contract including logs, summaries,
and execution stats.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forge.core.domain.interfaces import IMemoryRepository
from forge.core.domain.models import (
    ContextSummary,
    Execution,
    LogEntry,
    LogLevel,
    Task,
    TaskStatus,
    TaskType,
    TokenUsage,
)
from forge.infrastructure.db.models import (
    Base,
    ContextSummaryModel,
    ExecutionModel,
    LogEntryModel,
    TaskModel,
)

logger = logging.getLogger(__name__)


class SQLiteMemoryRepository(IMemoryRepository):
    """Async SQLite repository backed by SQLAlchemy 2.0 + aiosqlite."""

    def __init__(self, db_url: str = "sqlite+aiosqlite:///./forge.db") -> None:
        self._engine = create_async_engine(db_url, echo=False)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self) -> None:
        """Create all tables if they do not already exist."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialised")

    # ── Domain ↔ ORM Conversions ──────────────────────────────────────────────

    def _execution_to_domain(self, model: ExecutionModel) -> Execution:
        """Convert an ExecutionModel row to an Execution domain object."""
        token_data = model.token_usage_json or {}
        return Execution(
            id=UUID(str(model.id)),
            goal=model.goal,
            status=TaskStatus(model.status),
            started_at=model.started_at,
            completed_at=model.completed_at,
            token_usage=TokenUsage(**token_data) if token_data else TokenUsage(),
            error=model.error,
            metadata=model.metadata_json or {},
            tasks=[],  # populated separately to avoid N+1
        )

    def _task_to_domain(self, model: TaskModel) -> Task:
        """Convert a TaskModel row to a Task domain object."""
        return Task(
            id=UUID(str(model.id)),
            execution_id=UUID(str(model.execution_id)),
            name=model.name,
            description=model.description or "",
            task_type=TaskType(model.task_type),
            status=TaskStatus(model.status),
            order_index=model.order_index or 0,
            dependencies=[UUID(str(d)) for d in (model.dependencies or [])],
            inputs=model.inputs or {},
            outputs=model.outputs or {},
            error=model.error,
            started_at=model.started_at,
            completed_at=model.completed_at,
            retry_count=model.retry_count or 0,
            max_retries=model.max_retries or 3,
            estimated_duration_seconds=model.estimated_duration_seconds,
        )

    def _log_to_domain(self, model: LogEntryModel) -> LogEntry:
        """Convert a LogEntryModel row to a LogEntry domain object."""
        return LogEntry(
            id=UUID(str(model.id)),
            execution_id=UUID(str(model.execution_id)),
            task_id=UUID(str(model.task_id)) if model.task_id else None,
            level=LogLevel(model.level),
            message=model.message,
            details=model.details_json or {},
            timestamp=model.timestamp or datetime.utcnow(),
        )

    def _summary_to_domain(self, model: ContextSummaryModel) -> ContextSummary:
        """Convert a ContextSummaryModel row to a ContextSummary domain object."""
        return ContextSummary(
            id=UUID(str(model.id)),
            execution_id=UUID(str(model.execution_id)),
            summary=model.summary or "",
            token_count=model.token_count or 0,
            created_at=model.created_at or datetime.utcnow(),
            updated_at=model.updated_at or datetime.utcnow(),
        )

    # ── Execution CRUD ────────────────────────────────────────────────────────

    async def save_execution(self, execution: Execution) -> None:
        """Upsert an Execution (insert on first call, update on subsequent)."""
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ExecutionModel).where(
                        ExecutionModel.id == str(execution.id)
                    )
                )
                existing = result.scalar_one_or_none()
                token_dict = execution.token_usage.model_dump()
                if existing:
                    existing.goal = execution.goal
                    existing.status = execution.status.value
                    existing.started_at = execution.started_at
                    existing.completed_at = execution.completed_at
                    existing.token_usage_json = token_dict
                    existing.error = execution.error
                    existing.metadata_json = execution.metadata
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(
                        ExecutionModel(
                            id=str(execution.id),
                            goal=execution.goal,
                            status=execution.status.value,
                            started_at=execution.started_at,
                            completed_at=execution.completed_at,
                            token_usage_json=token_dict,
                            error=execution.error,
                            metadata_json=execution.metadata,
                        )
                    )

    async def get_execution(self, execution_id: UUID) -> Optional[Execution]:
        """Return an Execution with its tasks, or None if not found."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ExecutionModel).where(
                    ExecutionModel.id == str(execution_id)
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            domain = self._execution_to_domain(model)
            domain.tasks = await self.get_tasks_by_execution(execution_id)
            return domain

    async def list_executions(self, limit: int = 100) -> List[Execution]:
        """Return the most recent *limit* executions (newest first)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ExecutionModel)
                .order_by(ExecutionModel.created_at.desc())
                .limit(limit)
            )
            models = result.scalars().all()
            executions: List[Execution] = []
            for m in models:
                domain = self._execution_to_domain(m)
                domain.tasks = await self.get_tasks_by_execution(
                    UUID(str(m.id))
                )
                executions.append(domain)
            return executions

    # ── Task CRUD ─────────────────────────────────────────────────────────────

    async def save_task(self, task: Task) -> None:
        """Upsert a Task."""
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(TaskModel).where(TaskModel.id == str(task.id))
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.name = task.name
                    existing.description = task.description
                    existing.task_type = task.task_type.value
                    existing.status = task.status.value
                    existing.order_index = task.order_index
                    existing.dependencies = [str(d) for d in task.dependencies]
                    existing.inputs = task.inputs
                    existing.outputs = task.outputs
                    existing.error = task.error
                    existing.started_at = task.started_at
                    existing.completed_at = task.completed_at
                    existing.retry_count = task.retry_count
                    existing.max_retries = task.max_retries
                    existing.estimated_duration_seconds = task.estimated_duration_seconds
                else:
                    session.add(
                        TaskModel(
                            id=str(task.id),
                            execution_id=str(task.execution_id),
                            name=task.name,
                            description=task.description,
                            task_type=task.task_type.value,
                            status=task.status.value,
                            order_index=task.order_index,
                            dependencies=[str(d) for d in task.dependencies],
                            inputs=task.inputs,
                            outputs=task.outputs,
                            error=task.error,
                            started_at=task.started_at,
                            completed_at=task.completed_at,
                            retry_count=task.retry_count,
                            max_retries=task.max_retries,
                            estimated_duration_seconds=task.estimated_duration_seconds,
                        )
                    )

    async def get_task(self, task_id: UUID) -> Optional[Task]:
        """Return a single Task by ID, or None if not found."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.id == str(task_id))
            )
            model = result.scalar_one_or_none()
            return self._task_to_domain(model) if model else None

    async def get_tasks_by_execution(self, execution_id: UUID) -> List[Task]:
        """Return all tasks for an execution, ordered by order_index."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskModel)
                .where(TaskModel.execution_id == str(execution_id))
                .order_by(TaskModel.order_index)
            )
            return [self._task_to_domain(m) for m in result.scalars().all()]

    # ── Log CRUD ──────────────────────────────────────────────────────────────

    async def save_log(self, log: LogEntry) -> None:
        """Persist a structured log entry (always insert — logs are immutable)."""
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    LogEntryModel(
                        id=str(log.id),
                        execution_id=str(log.execution_id),
                        task_id=str(log.task_id) if log.task_id else None,
                        level=log.level.value,
                        message=log.message,
                        details_json=log.details,
                        timestamp=log.timestamp,
                    )
                )

    async def get_logs(
        self,
        execution_id: UUID,
        limit: int = 100,
        level: Optional[LogLevel] = None,
    ) -> List[LogEntry]:
        """Return log entries for an execution, newest first.

        Args:
            execution_id: Filter by this execution.
            limit: Maximum number of entries to return.
            level: Optional filter by log level.
        """
        async with self._session_factory() as session:
            query = (
                select(LogEntryModel)
                .where(LogEntryModel.execution_id == str(execution_id))
                .order_by(LogEntryModel.timestamp.desc())
                .limit(limit)
            )
            if level is not None:
                query = query.where(LogEntryModel.level == level.value)
            result = await session.execute(query)
            return [self._log_to_domain(m) for m in result.scalars().all()]

    # ── Summary CRUD ──────────────────────────────────────────────────────────

    async def save_summary(self, summary: ContextSummary) -> None:
        """Upsert the context summary for an execution."""
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ContextSummaryModel).where(
                        ContextSummaryModel.execution_id == str(summary.execution_id)
                    )
                )
                existing = result.scalar_one_or_none()
                now = datetime.utcnow()
                if existing:
                    existing.summary = summary.summary
                    existing.token_count = summary.token_count
                    existing.updated_at = now
                else:
                    session.add(
                        ContextSummaryModel(
                            id=str(summary.id),
                            execution_id=str(summary.execution_id),
                            summary=summary.summary,
                            token_count=summary.token_count,
                            created_at=summary.created_at,
                            updated_at=summary.updated_at,
                        )
                    )

    async def get_summary(self, execution_id: UUID) -> Optional[ContextSummary]:
        """Return the context summary for an execution, or None."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ContextSummaryModel).where(
                    ContextSummaryModel.execution_id == str(execution_id)
                )
            )
            model = result.scalar_one_or_none()
            return self._summary_to_domain(model) if model else None

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_execution_stats(self, execution_id: UUID) -> Dict[str, Any]:
        """Return aggregated statistics for a single execution.

        Returns a dict with keys: total_tasks, completed, failed, pending,
        in_progress, skipped, total_retries, duration_seconds.
        """
        async with self._session_factory() as session:
            # Task counts by status
            count_result = await session.execute(
                select(TaskModel.status, func.count(TaskModel.id).label("cnt"))
                .where(TaskModel.execution_id == str(execution_id))
                .group_by(TaskModel.status)
            )
            status_counts: Dict[str, int] = {
                row.status: row.cnt for row in count_result.all()
            }

            # Retry totals
            retry_result = await session.execute(
                select(func.sum(TaskModel.retry_count)).where(
                    TaskModel.execution_id == str(execution_id)
                )
            )
            total_retries: int = retry_result.scalar_one() or 0

            # Execution duration
            exec_result = await session.execute(
                select(ExecutionModel.started_at, ExecutionModel.completed_at).where(
                    ExecutionModel.id == str(execution_id)
                )
            )
            exec_row = exec_result.first()
            duration: Optional[float] = None
            if exec_row and exec_row.started_at and exec_row.completed_at:
                duration = (
                    exec_row.completed_at - exec_row.started_at
                ).total_seconds()

            total = sum(status_counts.values())
            return {
                "total_tasks": total,
                "completed": status_counts.get("completed", 0),
                "failed": status_counts.get("failed", 0),
                "pending": status_counts.get("pending", 0),
                "in_progress": status_counts.get("in_progress", 0),
                "skipped": status_counts.get("skipped", 0),
                "cancelled": status_counts.get("cancelled", 0),
                "total_retries": total_retries,
                "duration_seconds": duration,
            }
