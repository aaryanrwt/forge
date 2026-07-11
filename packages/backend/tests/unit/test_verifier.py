"""Unit tests for task output verifiers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from forge.application.services.verifier import (
    ExitCodeVerifier,
    FileExistsVerifier,
    OutputPatternVerifier,
    TaskStatusVerifier,
)
from forge.core.domain.models import Task, TaskStatus, TaskType


@pytest.mark.asyncio
async def test_task_status_verifier() -> None:
    v = TaskStatusVerifier()
    task = Task(
        execution_id=uuid4(),
        name="",
        description="",
        task_type=TaskType.SHELL,
        status=TaskStatus.COMPLETED,
    )

    res = await v.verify(task)
    assert res.success is True

    task.status = TaskStatus.FAILED
    res = await v.verify(task)
    assert res.success is False


@pytest.mark.asyncio
async def test_exit_code_verifier() -> None:
    v = ExitCodeVerifier()

    # 0 exit code = Success
    task_success = Task(
        execution_id=uuid4(),
        name="",
        description="",
        task_type=TaskType.SHELL,
        outputs={"returncode": 0},
    )
    res = await v.verify(task_success)
    assert res.success is True

    # Non-zero exit code = Failure
    task_fail = Task(
        execution_id=uuid4(),
        name="",
        description="",
        task_type=TaskType.SHELL,
        outputs={"returncode": 127},
    )
    res = await v.verify(task_fail)
    assert res.success is False


@pytest.mark.asyncio
async def test_file_exists_verifier(tmp_path: object) -> None:  # type: ignore[override]
    v = FileExistsVerifier()

    # Temp file to verify
    test_file = str(tmp_path / "output.txt")  # type: ignore[attr-defined]

    task = Task(
        execution_id=uuid4(),
        name="",
        description="",
        task_type=TaskType.SHELL,
        inputs={"expected_files": [test_file]},
    )

    # File doesn't exist yet
    res = await v.verify(task)
    assert res.success is False

    # Create file
    with open(test_file, "w") as f:
        f.write("hello")

    res = await v.verify(task)
    assert res.success is True


@pytest.mark.asyncio
async def test_output_pattern_verifier() -> None:
    v = OutputPatternVerifier()
    task = Task(
        execution_id=uuid4(),
        name="",
        description="",
        task_type=TaskType.SHELL,
        inputs={"expected_pattern": r"Database connected successfully"},
        outputs={"stdout": "Some logs...\nDatabase connected successfully\nServer started."},
    )

    res = await v.verify(task)
    assert res.success is True

    # Output mismatch
    task.outputs = {"stdout": "Connection failed."}
    res = await v.verify(task)
    assert res.success is False
