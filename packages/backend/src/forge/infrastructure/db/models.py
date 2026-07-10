"""SQLAlchemy ORM models for Forge's SQLite persistence layer.

Each ORM model maps 1-to-1 with a domain aggregate or value object.
Conversion between ORM and domain models is handled in the repository layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import TEXT as SQLITE_TEXT
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import TypeDecorator, CHAR
import uuid as _uuid_module


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

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    goal = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    token_usage_json = Column(JSON, default=dict, nullable=False)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
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

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUIDType, ForeignKey("executions.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    task_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    dependencies = Column(JSON, default=list, nullable=False)
    inputs = Column(JSON, default=dict, nullable=False)
    outputs = Column(JSON, default=dict, nullable=False)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    estimated_duration_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    execution = relationship("ExecutionModel", back_populates="tasks")


class LogEntryModel(Base):
    """Persists a structured log entry for an execution."""

    __tablename__ = "log_entries"
    __table_args__ = (
        Index("ix_log_entries_execution_id", "execution_id"),
        Index("ix_log_entries_level", "level"),
        Index("ix_log_entries_timestamp", "timestamp"),
    )

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUIDType, ForeignKey("executions.id"), nullable=False)
    task_id = Column(UUIDType, nullable=True)
    level = Column(String(16), nullable=False, default="info")
    message = Column(Text, nullable=False)
    details_json = Column(JSON, default=dict, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    execution = relationship("ExecutionModel", back_populates="logs")


class ContextSummaryModel(Base):
    """Persists a rolling context summary for an execution (one per execution)."""

    __tablename__ = "context_summaries"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_context_summary_execution"),
    )

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUIDType, ForeignKey("executions.id"), nullable=False)
    summary = Column(Text, nullable=False, default="")
    token_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    execution = relationship("ExecutionModel", back_populates="summary")
