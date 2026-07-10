"""Forge executor services — CLI, Shell, Python, Git, Docker, MCP, Model.

Each executor implements IExecutor and handles one or more TaskTypes.
The ExecutorService acts as a dispatcher that selects the right executor for
each task and applies a configurable timeout.

Executors in v1.0:
- ``ShellExecutor`` (CLI + SHELL): runs shell commands via asyncio subprocess
- ``PythonExecutor``: executes Python code snippets in a restricted namespace
- ``GitExecutor``: git clone/status/diff/commit (no push for safety)
- ``DockerExecutor``: docker build/run/ps (read-heavy operations only)
- ``MCPExecutor``: delegates to an MCPClient tool call
- ``ModelExecutor``: calls an LLM provider directly as a task
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional

from forge.core.domain.exceptions import ExecutorError
from forge.core.domain.interfaces import IExecutor, ILLMProvider
from forge.core.domain.models import Task, TaskStatus, TaskType, TokenUsage
from forge.infrastructure.mcp.mcp_client import MCPClient, StdioTransport

logger = logging.getLogger(__name__)


# ── Helper ───────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.utcnow()


def _mark_started(task: Task) -> None:
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = _now()


def _mark_completed(task: Task, outputs: Dict[str, Any]) -> None:
    task.status = TaskStatus.COMPLETED
    task.outputs = outputs
    task.completed_at = _now()


def _mark_failed(task: Task, error: str) -> None:
    task.status = TaskStatus.FAILED
    task.error = error
    task.completed_at = _now()


# ── Shell / CLI Executor ──────────────────────────────────────────────────────


class ShellExecutor(IExecutor):
    """Runs shell commands via asyncio subprocess with a configurable timeout.

    Inputs:
        command (str): Shell command to execute.
        cwd (str, optional): Working directory.
        env (dict, optional): Additional environment variables.

    Outputs:
        stdout (str), stderr (str), returncode (int)
    """

    def __init__(self, timeout: int = 60) -> None:
        self._timeout = timeout

    def supports(self, task_type: TaskType) -> bool:
        return task_type in (TaskType.SHELL, TaskType.CLI)

    async def execute(self, task: Task) -> Task:
        _mark_started(task)
        command: str = task.inputs.get("command", "")
        if not command:
            _mark_failed(task, "No 'command' provided in task inputs")
            return task

        cwd: Optional[str] = task.inputs.get("cwd")
        env: Optional[Dict[str, str]] = task.inputs.get("env")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")

            if proc.returncode == 0:
                _mark_completed(
                    task,
                    {"stdout": stdout, "stderr": stderr, "returncode": proc.returncode},
                )
            else:
                _mark_failed(
                    task,
                    f"Command exited with code {proc.returncode}: {stderr or stdout}",
                )
        except asyncio.TimeoutError:
            _mark_failed(task, f"Command timed out after {self._timeout}s: {command}")
        except Exception as exc:
            _mark_failed(task, str(exc))

        return task


# Alias for backward compatibility
CLIExecutor = ShellExecutor


# ── Python Executor ───────────────────────────────────────────────────────────


class PythonExecutor(IExecutor):
    """Executes Python code snippets in an isolated namespace.

    Inputs:
        code (str): Python source code to execute.

    Outputs:
        result (Any): Value of the ``result`` variable if set in the snippet.
        stdout (str): Captured standard output.

    Security note: exec() is not a sandbox.  Do not expose this executor to
    untrusted input in production.  Restrict via network policies or use a
    subprocess-based sandbox instead.
    """

    def __init__(self, timeout: int = 60) -> None:
        self._timeout = timeout

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.PYTHON

    async def execute(self, task: Task) -> Task:
        _mark_started(task)
        code: str = task.inputs.get("code", "")
        if not code:
            _mark_failed(task, "No 'code' provided in task inputs")
            return task

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._run_code, code
                ),
                timeout=self._timeout,
            )
            _mark_completed(task, result)
        except asyncio.TimeoutError:
            _mark_failed(task, f"Python execution timed out after {self._timeout}s")
        except Exception as exc:
            _mark_failed(task, str(exc))

        return task

    def _run_code(self, code: str) -> Dict[str, Any]:
        """Execute *code* in a fresh namespace and capture stdout."""
        import io
        import contextlib

        buf = io.StringIO()
        namespace: Dict[str, Any] = {}
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<forge>", "exec"), namespace)  # noqa: S102
        return {
            "result": namespace.get("result"),
            "stdout": buf.getvalue(),
        }


# ── Git Executor ──────────────────────────────────────────────────────────────


class GitExecutor(IExecutor):
    """Safe git operations: clone, status, diff, commit.

    Push is intentionally excluded to prevent accidental data loss.

    Inputs:
        operation (str): One of "clone", "status", "diff", "commit".
        repo_url (str, optional): Remote URL (clone only).
        path (str, optional): Local path for the operation.
        message (str, optional): Commit message (commit only).

    Outputs:
        stdout (str), stderr (str), returncode (int)
    """

    ALLOWED_OPERATIONS = {"clone", "status", "diff", "commit"}

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.GIT

    async def execute(self, task: Task) -> Task:
        _mark_started(task)
        operation: str = task.inputs.get("operation", "").lower()

        if operation not in self.ALLOWED_OPERATIONS:
            _mark_failed(
                task,
                f"Git operation '{operation}' is not allowed. "
                f"Allowed: {sorted(self.ALLOWED_OPERATIONS)}",
            )
            return task

        cmd = self._build_command(operation, task.inputs)
        if cmd is None:
            _mark_failed(task, f"Could not build git command for operation '{operation}'")
            return task

        cwd: Optional[str] = task.inputs.get("path")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")

            if proc.returncode == 0:
                _mark_completed(
                    task,
                    {"stdout": stdout, "stderr": stderr, "returncode": proc.returncode},
                )
            else:
                _mark_failed(task, f"git {operation} failed: {stderr or stdout}")
        except asyncio.TimeoutError:
            _mark_failed(task, f"git {operation} timed out after {self._timeout}s")
        except FileNotFoundError:
            _mark_failed(task, "git executable not found. Install git and ensure it is on PATH.")
        except Exception as exc:
            _mark_failed(task, str(exc))

        return task

    def _build_command(
        self, operation: str, inputs: Dict[str, Any]
    ) -> Optional[List[str]]:
        """Build the git argv list for the requested operation."""
        if operation == "clone":
            repo_url = inputs.get("repo_url", "")
            if not repo_url:
                return None
            cmd = ["git", "clone", repo_url]
            if path := inputs.get("path"):
                cmd.append(str(path))
            return cmd
        if operation == "status":
            return ["git", "status", "--short"]
        if operation == "diff":
            args = ["git", "diff"]
            if cached := inputs.get("cached"):
                args.append("--cached")
            return args
        if operation == "commit":
            message = inputs.get("message", "Auto-commit by Forge")
            return ["git", "commit", "-am", message]
        return None


# ── Docker Executor ───────────────────────────────────────────────────────────


class DockerExecutor(IExecutor):
    """Safe Docker operations: build, run, ps.

    Write-heavy operations (push, rm, rmi) are excluded from v1.0.

    Inputs:
        operation (str): One of "build", "run", "ps".
        args (list[str], optional): Extra CLI arguments.
        image (str, optional): Image name (build/run).
        context (str, optional): Build context path (build).
        command (str, optional): Command to run inside the container (run).

    Outputs:
        stdout (str), stderr (str), returncode (int)
    """

    ALLOWED_OPERATIONS = {"build", "run", "ps"}

    def __init__(self, timeout: int = 600) -> None:
        self._timeout = timeout

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.DOCKER

    async def execute(self, task: Task) -> Task:
        _mark_started(task)
        operation: str = task.inputs.get("operation", "").lower()

        if operation not in self.ALLOWED_OPERATIONS:
            _mark_failed(
                task,
                f"Docker operation '{operation}' is not allowed. "
                f"Allowed: {sorted(self.ALLOWED_OPERATIONS)}",
            )
            return task

        cmd = self._build_command(operation, task.inputs)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")

            if proc.returncode == 0:
                _mark_completed(
                    task,
                    {"stdout": stdout, "stderr": stderr, "returncode": proc.returncode},
                )
            else:
                _mark_failed(task, f"docker {operation} failed: {stderr or stdout}")
        except asyncio.TimeoutError:
            _mark_failed(task, f"docker {operation} timed out after {self._timeout}s")
        except FileNotFoundError:
            _mark_failed(
                task, "docker executable not found. Install Docker and ensure it is on PATH."
            )
        except Exception as exc:
            _mark_failed(task, str(exc))

        return task

    def _build_command(
        self, operation: str, inputs: Dict[str, Any]
    ) -> List[str]:
        extra_args: List[str] = inputs.get("args", [])
        if operation == "build":
            image = inputs.get("image", "forge-image")
            context = inputs.get("context", ".")
            return ["docker", "build", "-t", image, context] + extra_args
        if operation == "run":
            image = inputs.get("image", "")
            cmd_parts = ["docker", "run", "--rm"]
            cmd_parts += extra_args
            if image:
                cmd_parts.append(image)
            if run_cmd := inputs.get("command"):
                cmd_parts += run_cmd.split()
            return cmd_parts
        if operation == "ps":
            return ["docker", "ps"] + extra_args
        return ["docker"] + extra_args


# ── MCP Executor ──────────────────────────────────────────────────────────────


class MCPExecutor(IExecutor):
    """Delegates task execution to an MCP tool via MCPClient.

    Inputs:
        mcp_command (list[str]): Subprocess command to start the MCP server.
        tool_name (str): Name of the tool to call.
        tool_args (dict, optional): Arguments passed to the tool.
        mcp_url (str, optional): HTTP URL (used instead of mcp_command).

    Outputs:
        content (Any): Raw content returned by the MCP tool.
    """

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.MCP

    async def execute(self, task: Task) -> Task:
        _mark_started(task)
        tool_name: str = task.inputs.get("tool_name", "")
        if not tool_name:
            _mark_failed(task, "No 'tool_name' provided in task inputs")
            return task

        try:
            client = MCPClient()
            if mcp_url := task.inputs.get("mcp_url"):
                from forge.infrastructure.mcp.mcp_client import HTTPTransport
                transport = HTTPTransport(mcp_url)
            else:
                mcp_command: List[str] = task.inputs.get("mcp_command", [])
                if not mcp_command:
                    _mark_failed(task, "Either 'mcp_command' or 'mcp_url' must be provided")
                    return task
                transport = StdioTransport(command=mcp_command)

            async with client:
                await client.connect(transport)
                await client.initialize()
                content = await client.call_tool(
                    tool_name, task.inputs.get("tool_args", {})
                )
            _mark_completed(task, {"content": content})
        except Exception as exc:
            _mark_failed(task, str(exc))

        return task


# ── Model Executor ────────────────────────────────────────────────────────────


class ModelExecutor(IExecutor):
    """Calls an LLM provider directly as a task (prompt → response).

    Inputs:
        prompt (str): User message to send.
        system (str, optional): System message prefix.
        max_tokens (int, optional): Maximum tokens (default 2048).
        temperature (float, optional): Sampling temperature (default 0.1).

    Outputs:
        response (str): LLM response text.
        token_usage (dict): Prompt/completion/total token counts.
    """

    def __init__(self, llm: ILLMProvider) -> None:
        self._llm = llm

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.MODEL

    async def execute(self, task: Task) -> Task:
        _mark_started(task)
        prompt: str = task.inputs.get("prompt", "")
        if not prompt:
            _mark_failed(task, "No 'prompt' provided in task inputs")
            return task

        messages: List[Dict[str, str]] = []
        if system := task.inputs.get("system"):
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response, usage = await self._llm.complete(
                messages,
                max_tokens=int(task.inputs.get("max_tokens", 2048)),
                temperature=float(task.inputs.get("temperature", 0.1)),
            )
            _mark_completed(
                task,
                {
                    "response": response,
                    "token_usage": usage.model_dump(),
                },
            )
        except Exception as exc:
            _mark_failed(task, str(exc))

        return task


# ── Executor Service (Dispatcher) ─────────────────────────────────────────────


class ExecutorService:
    """Dispatches tasks to the first executor that claims to support them.

    If no executor supports a given task type, the task is marked FAILED.
    """

    def __init__(self, executors: List[IExecutor]) -> None:
        self._executors = executors

    def add_executor(self, executor: IExecutor) -> None:
        """Register an additional executor at runtime."""
        self._executors.append(executor)

    async def execute(self, task: Task) -> Task:
        """Find the first supporting executor and run *task* through it.

        Returns the mutated task with updated status/outputs/error.
        """
        for executor in self._executors:
            if executor.supports(task.task_type):
                logger.debug(
                    "Dispatching task %s (type=%s) to %s",
                    task.id,
                    task.task_type.value,
                    type(executor).__name__,
                )
                return await executor.execute(task)

        # No executor found — mark as failed
        task.status = TaskStatus.FAILED
        task.error = (
            f"No executor registered for task type '{task.task_type.value}'. "
            f"Available executors: "
            f"{[type(e).__name__ for e in self._executors]}"
        )
        task.completed_at = _now()
        return task
