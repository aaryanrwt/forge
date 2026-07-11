"""Unit tests for the built-in executors (Shell, Python, Git, Docker, Model, MCP)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from forge.application.services.executor import (
    DockerExecutor,
    GitExecutor,
    PythonExecutor,
    ShellExecutor,
)
from forge.core.domain.models import Task, TaskStatus, TaskType


@pytest.mark.asyncio
async def test_shell_executor_echo() -> None:
    exec = ShellExecutor(timeout=5)
    task = Task(
        execution_id=uuid4(),
        name="Echo hello",
        description="",
        task_type=TaskType.SHELL,
        inputs={"command": "echo hello_world"},
    )

    res = await exec.execute(task)
    assert res.status == TaskStatus.COMPLETED
    assert "hello_world" in res.outputs["stdout"]
    assert res.outputs["returncode"] == 0


@pytest.mark.asyncio
async def test_shell_executor_timeout() -> None:
    # 1 second timeout
    exec = ShellExecutor(timeout=1)

    # Run command that sleeps for 3 seconds using python
    cmd = 'python -c "import time; time.sleep(3)"'
    task = Task(
        execution_id=uuid4(),
        name="Sleep command",
        description="",
        task_type=TaskType.SHELL,
        inputs={"command": cmd},
    )

    res = await exec.execute(task)
    assert res.status == TaskStatus.FAILED
    assert "timed out" in res.error.lower()


@pytest.mark.asyncio
async def test_python_executor_success() -> None:
    exec = PythonExecutor()
    task = Task(
        execution_id=uuid4(),
        name="Run simple math",
        description="",
        task_type=TaskType.PYTHON,
        inputs={"code": "x = 10\ny = 20\nresult = x + y\nprint('Done math')"},
    )

    res = await exec.execute(task)
    assert res.status == TaskStatus.COMPLETED
    assert res.outputs["result"] == 30
    assert "Done math" in res.outputs["stdout"]


@pytest.mark.asyncio
async def test_git_executor_blocked_operations() -> None:
    exec = GitExecutor()

    # Try git push (which should be blocked)
    task_push = Task(
        execution_id=uuid4(),
        name="Push branch",
        description="",
        task_type=TaskType.GIT,
        inputs={"operation": "push"},
    )
    res_push = await exec.execute(task_push)
    assert res_push.status == TaskStatus.FAILED
    assert "not allowed" in res_push.error.lower()

    # Try git clone (which is allowed)
    task_clone = Task(
        execution_id=uuid4(),
        name="Clone repo",
        description="",
        task_type=TaskType.GIT,
        inputs={
            "operation": "clone",
            "repo_url": "",
        },  # empty URL fails command building but passes safety
    )
    res_clone = await exec.execute(task_clone)
    assert res_clone.status == TaskStatus.FAILED
    assert "could not build git command" in res_clone.error.lower()


@pytest.mark.asyncio
async def test_docker_executor_blocked_operations() -> None:
    exec = DockerExecutor()

    # Try docker push (blocked)
    task_push = Task(
        execution_id=uuid4(),
        name="Push image",
        description="",
        task_type=TaskType.DOCKER,
        inputs={"operation": "push", "args": ["my-image"]},
    )
    res_push = await exec.execute(task_push)
    assert res_push.status == TaskStatus.FAILED
    assert "not allowed" in res_push.error.lower()

    # Try docker ps (allowed)
    task_ps = Task(
        execution_id=uuid4(),
        name="List containers",
        description="",
        task_type=TaskType.DOCKER,
        inputs={"operation": "ps"},
    )
    res_ps = await exec.execute(task_ps)
    # On environments without docker daemon running, this will fail with 'daemon not running' or 'executable not found',
    # but the command builder itself should have allowed the operation.
    assert res_ps.status in (TaskStatus.FAILED, TaskStatus.COMPLETED)
    if res_ps.status == TaskStatus.FAILED:
        assert "not allowed" not in res_ps.error.lower()
