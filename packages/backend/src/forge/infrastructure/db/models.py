"""SQLAlchemy ORM models for Forge's SQLite persistence layer.

Each ORM model maps 1-to-1 with a domain aggregate or value object.
Conversion between ORM and domain models is handled in the repository layer.
"""

from __future__ import annotations

import uuid
import uuid as _uuid_module
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, TypeDecorator


class UUIDType(TypeDecorator):  # type: ignore[type-arg]
    """Platform-independent UUID type stored as CHAR(36)."""

    impl = CHAR
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(36)

    def process_bind_param(self, value: object, dialect: object) -> object:
        if value is None:
            return value
        if isinstance(value, _uuid_module.UUID):
            return str(value)
        return str(_uuid_module.UUID(str(value)))

    def process_result_value(self, value: object, dialect: object) -> object:
        if value is None:
            return value
        return _uuid_module.UUID(str(value))


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class ExecutionModel(Base):
    """Persists an Execution aggregate root."""

    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    tasks = relationship(
        "TaskModel",
        back_populates="execution",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="TaskModel.order_index",
    )
    logs = relationship(
        "LogEntryModel",
        back_populates="execution",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="LogEntryModel.timestamp",
    )
    summary = relationship(
        "ContextSummaryModel",
        back_populates="execution",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select",
    )


class TaskModel(Base):
    """Persists a Task entity."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_execution_id", "execution_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_order", "execution_id", "order_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("executions.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    estimated_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    execution = relationship("ExecutionModel", back_populates="tasks")


class LogEntryModel(Base):
    """Persists a structured log entry for an execution."""

    __tablename__ = "log_entries"
    __table_args__ = (
        Index("ix_log_entries_execution_id", "execution_id"),
        Index("ix_log_entries_level", "level"),
        Index("ix_log_entries_timestamp", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("executions.id"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    execution = relationship("ExecutionModel", back_populates="logs")


class ContextSummaryModel(Base):
    """Persists a rolling context summary for an execution (one per execution)."""

    __tablename__ = "context_summaries"
    __table_args__ = (UniqueConstraint("execution_id", name="uq_context_summary_execution"),)

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("executions.id"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    execution = relationship("ExecutionModel", back_populates="summary")
