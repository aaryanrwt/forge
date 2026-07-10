"""Forge verifiers — inspects task output to verify correctness.

Implements discrete check logic (ExitCode, FileExists, OutputPattern) and a
`CompositeVerifier` that aggregates multiple verifiers.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List
from forge.core.domain.interfaces import IVerifier
from forge.core.domain.models import Task, TaskStatus, VerificationResult

logger = logging.getLogger(__name__)


class TaskStatusVerifier(IVerifier):
    """Verifies that the task status is set to COMPLETED."""

    async def verify(self, task: Task) -> VerificationResult:
        if task.status == TaskStatus.COMPLETED:
            return VerificationResult(
                success=True,
                message="Task status is completed",
            )
        return VerificationResult(
            success=False,
            message=f"Task is in state '{task.status.value}', expected completed",
            details={"status": task.status.value, "error": task.error},
        )


class ExitCodeVerifier(IVerifier):
    """Verifies that a command execution exited with a return code of 0.

    Examines task outputs for 'returncode'.
    """

    async def verify(self, task: Task) -> VerificationResult:
        # If output does not have a returncode, this verifier passes implicitly
        # (intended for tasks that don't involve subprocess execution)
        if "returncode" not in task.outputs:
            return VerificationResult(
                success=True,
                message="Implicit success: No returncode present to verify",
            )

        rc = task.outputs["returncode"]
        if rc == 0:
            return VerificationResult(
                success=True,
                message="Exit code is 0",
            )
        return VerificationResult(
            success=False,
            message=f"Command failed with non-zero exit code: {rc}",
            details={"returncode": rc, "stderr": task.outputs.get("stderr")},
        )


class FileExistsVerifier(IVerifier):
    """Verifies that required output files were created on disk.

    Examines task inputs for 'expected_files' (list of paths).
    """

    async def verify(self, task: Task) -> VerificationResult:
        expected_files = task.inputs.get("expected_files")
        if not expected_files:
            return VerificationResult(
                success=True,
                message="No expected output files specified to verify",
            )

        if isinstance(expected_files, str):
            expected_files = [expected_files]

        missing = []
        for file_path in expected_files:
            if not os.path.exists(file_path):
                missing.append(file_path)

        if not missing:
            return VerificationResult(
                success=True,
                message="All expected output files exist",
                details={"verified_files": expected_files},
            )

        return VerificationResult(
            success=False,
            message=f"Missing expected output files: {', '.join(missing)}",
            details={"missing_files": missing},
        )


class OutputPatternVerifier(IVerifier):
    """Verifies that command output contains or matches a specified pattern.

    Examines task inputs for 'expected_pattern' (regex string).
    """

    async def verify(self, task: Task) -> VerificationResult:
        pattern = task.inputs.get("expected_pattern")
        if not pattern:
            return VerificationResult(
                success=True,
                message="No output pattern validation specified",
            )

        stdout = task.outputs.get("stdout", "")
        try:
            regex = re.compile(pattern, re.DOTALL)
            if regex.search(stdout):
                return VerificationResult(
                    success=True,
                    message=f"Output matched expected pattern: '{pattern}'",
                )
            return VerificationResult(
                success=False,
                message=f"Output did not match expected pattern: '{pattern}'",
                details={"stdout_preview": stdout[:500]},
            )
        except re.error as exc:
            return VerificationResult(
                success=False,
                message=f"Invalid verification regex pattern: '{pattern}'",
                details={"regex_error": str(exc)},
            )


class CompositeVerifier(IVerifier):
    """Chains multiple verifiers in sequence.

    Fails at the first verifier that returns success=False.
    """

    def __init__(self, verifiers: List[IVerifier]) -> None:
        """Initialize composite verifier.

        Args:
            verifiers: List of underlying verifier instances.
        """
        self.verifiers = verifiers

    async def verify(self, task: Task) -> VerificationResult:
        """Run all verifiers sequentially."""
        for v in self.verifiers:
            res = await v.verify(task)
            if not res.success:
                logger.warning(
                    "Verification failed at step %s: %s",
                    type(v).__name__,
                    res.message,
                )
                return res

        return VerificationResult(
            success=True,
            message="All verifications passed",
        )


# Backward compatibility default
SimpleVerifier = CompositeVerifier
