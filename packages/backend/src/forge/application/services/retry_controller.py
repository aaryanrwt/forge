"""Forge retry controller — circuit breakers, backoffs, and infinite loop detection.

Implements a retry decision system combining exponential backoff, error keyword
classification, sliding-window circuit breakers, and infinite loop state detection.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID

from forge.core.domain.interfaces import IRetryController
from forge.core.domain.models import (
    CircuitBreakerState,
    FailureType,
    RetryDecision,
    Task,
)

logger = logging.getLogger(__name__)


class InfiniteLoopDetector:
    """Detects if execution is trapped in an infinite retry loop.

    Tracks hashes of (task_name, task_inputs, task_error) to identify cycle repetition.
    If a identical failure is seen 3 or more times, an infinite loop is flagged.
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        # Maps execution_id -> dict of {hash -> count}
        self._history: Dict[UUID, Dict[str, int]] = {}

    def _hash_state(self, task: Task, error: Optional[str]) -> str:
        """Create a unique MD5 hash representing the task state and failure error."""
        inputs_serialized = ""
        try:
            inputs_serialized = json.dumps(task.inputs, sort_keys=True)
        except Exception:
            inputs_serialized = str(task.inputs)

        raw = f"{task.name}:{inputs_serialized}:{error or ''}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()  # noqa: S324

    def record_and_check(self, task: Task, error: Optional[str]) -> bool:
        """Record the current task failure and return True if a loop is detected."""
        cycle_hash = self._hash_state(task, error)
        exec_id = task.execution_id

        if exec_id not in self._history:
            self._history[exec_id] = {}

        counts = self._history[exec_id]
        counts[cycle_hash] = counts.get(cycle_hash, 0) + 1

        logger.debug(
            "Loop detector tracking task %s failure hash %s: count=%d",
            task.id,
            cycle_hash[:8],
            counts[cycle_hash],
        )

        return counts[cycle_hash] >= self.threshold

    def clear(self, execution_id: UUID) -> None:
        """Clear loop history for a given execution."""
        self._history.pop(execution_id, None)


class CircuitBreaker:
    """Circuit breaker for a specific executor type or task name.

    If failure counts exceed a threshold within a sliding window,
    the circuit opens and rejects execution requests until a timeout expires.
    """

    def __init__(
        self,
        name: str,
        threshold: int = 5,
        timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.threshold = threshold
        self.timeout = timeout
        
        self.state = CircuitBreakerState.CLOSED
        self.failures: List[float] = []
        self.last_state_change = time.time()

    def record_failure(self) -> None:
        """Record a failure event and update circuit state."""
        now = time.time()
        self.failures.append(now)

        # Cleanup failures outside window (e.g. 5 minutes)
        self.failures = [f for f in self.failures if now - f < 300]

        if self.state == CircuitBreakerState.CLOSED and len(self.failures) >= self.threshold:
            self.state = CircuitBreakerState.OPEN
            self.last_state_change = now
            logger.warning(
                "Circuit breaker '%s' OPENED. Failure threshold %d exceeded.",
                self.name,
                self.threshold,
            )
        elif self.state == CircuitBreakerState.HALF_OPEN:
            # Any failure in half-open state puts it back to open
            self.state = CircuitBreakerState.OPEN
            self.last_state_change = now
            logger.warning("Circuit breaker '%s' returned to OPEN from HALF-OPEN", self.name)

    def record_success(self) -> None:
        """Record a success event and close the circuit if it was open/half-open."""
        if self.state != CircuitBreakerState.CLOSED:
            logger.info("Circuit breaker '%s' CLOSED (recovered on success)", self.name)
            self.state = CircuitBreakerState.CLOSED
            self.failures.clear()
            self.last_state_change = time.time()

    def allow_execution(self) -> bool:
        """Check if execution is allowed. Transitions OPEN -> HALF_OPEN if timeout elapsed."""
        now = time.time()
        if self.state == CircuitBreakerState.OPEN:
            if now - self.last_state_change >= self.timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.last_state_change = now
                logger.info("Circuit breaker '%s' transitioned to HALF-OPEN (testing recovery)", self.name)
                return True
            return False
        return True


class CircuitBreakerRetryController(IRetryController):
    """Combines circuit breakers, loop detection, and exponential backoff."""

    TRANSIENT_KEYWORDS = [
        "timeout", "connection", "rate limit", "429", "503", "temporary",
        "busy", "service unavailable", "try again", "network",
    ]

    PERMANENT_KEYWORDS = [
        "not found", "permission denied", "unauthorized", "401", "403", "404",
        "syntaxerror", "validation error", "invalid argument", "bad request",
    ]

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        circuit_threshold: int = 5,
        circuit_timeout: float = 60.0,
    ) -> None:
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

        self.loop_detector = InfiniteLoopDetector()
        self._circuit_threshold = circuit_threshold
        self._circuit_timeout = circuit_timeout
        self._circuits: Dict[str, CircuitBreaker] = {}

    def _get_circuit(self, task_type_value: str) -> CircuitBreaker:
        if task_type_value not in self._circuits:
            self._circuits[task_type_value] = CircuitBreaker(
                name=task_type_value,
                threshold=self._circuit_threshold,
                timeout=self._circuit_timeout,
            )
        return self._circuits[task_type_value]

    async def decide(self, task: Task, error: Optional[str] = None) -> RetryDecision:
        """Produce a RetryDecision based on the task, failure count, error, and circuit breakers."""
        # 1. Loop detection
        if self.loop_detector.record_and_check(task, error):
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                failure_type=FailureType.PERMANENT,
                reason="Infinite retry loop detected (identical inputs and errors repeated).",
            )

        # 2. Check retry budget
        if task.retry_count >= task.max_retries:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                failure_type=FailureType.PERMANENT,
                reason=f"Exceeded max retries budget of {task.max_retries}.",
            )

        # 3. Classify error type
        failure_type = self._classify_error(error)

        # 4. If permanent, fail immediately
        if failure_type == FailureType.PERMANENT:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                failure_type=FailureType.PERMANENT,
                reason="Permanent failure classified (validation/syntax/permission).",
            )

        # 5. Record failure in the circuit breaker for this task type
        circuit = self._get_circuit(task.task_type.value)
        circuit.record_failure()

        # Check if circuit is open
        if not circuit.allow_execution():
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                failure_type=FailureType.TRANSIENT,
                reason=f"Circuit breaker for executor '{task.task_type.value}' is OPEN.",
            )

        # 6. Exponential backoff calculation
        delay = min(
            self.initial_delay * (self.backoff_factor ** task.retry_count),
            self.max_delay,
        )

        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            failure_type=failure_type,
            reason="Transient/unknown failure — executing backoff retry.",
        )

    def record_success(self, task: Task) -> None:
        """Call this on successful execution to close the circuit for the task type."""
        circuit = self._get_circuit(task.task_type.value)
        circuit.record_success()

    def _classify_error(self, error: Optional[str]) -> FailureType:
        if not error:
            return FailureType.UNKNOWN

        error_lower = error.lower()

        for k in self.PERMANENT_KEYWORDS:
            if k in error_lower:
                return FailureType.PERMANENT

        for k in self.TRANSIENT_KEYWORDS:
            if k in error_lower:
                return FailureType.TRANSIENT

        return FailureType.UNKNOWN


# Alias for backwards compatibility
SimpleRetryController = CircuitBreakerRetryController
