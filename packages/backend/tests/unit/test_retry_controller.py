"""Unit tests for the circuit-breaker retry controller and loop detector."""
from __future__ import annotations

import time
from uuid import uuid4
import pytest

from forge.application.services.retry_controller import (
    CircuitBreaker,
    CircuitBreakerRetryController,
    InfiniteLoopDetector,
)
from forge.core.domain.models import CircuitBreakerState, FailureType, Task, TaskType


def test_infinite_loop_detector() -> None:
    detector = InfiniteLoopDetector(threshold=3)
    task = Task(execution_id=uuid4(), name="Install package", description="", task_type=TaskType.SHELL)
    error = "Could not find a version that satisfies the requirement"

    # First and second calls should not flag loop
    assert detector.record_and_check(task, error) is False
    assert detector.record_and_check(task, error) is False
    
    # Third call flags loop
    assert detector.record_and_check(task, error) is True


def test_circuit_breaker_transitions() -> None:
    breaker = CircuitBreaker(name="mcp", threshold=3, timeout=0.1)
    
    assert breaker.state == CircuitBreakerState.CLOSED
    assert breaker.allow_execution() is True

    # Trigger 3 failures to open circuit
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    
    assert breaker.state == CircuitBreakerState.OPEN
    assert breaker.allow_execution() is False

    # Sleep to trigger timeout transition to HALF_OPEN
    time.sleep(0.12)
    assert breaker.allow_execution() is True
    assert breaker.state == CircuitBreakerState.HALF_OPEN

    # A failure in half-open opens it again
    breaker.record_failure()
    assert breaker.state == CircuitBreakerState.OPEN
    assert breaker.allow_execution() is False

    # Sleep again to test recovery
    time.sleep(0.12)
    assert breaker.allow_execution() is True
    
    # Success closes it
    breaker.record_success()
    assert breaker.state == CircuitBreakerState.CLOSED
    assert breaker.allow_execution() is True


@pytest.mark.asyncio
async def test_retry_controller_decision_transient() -> None:
    controller = CircuitBreakerRetryController(
        initial_delay=1.0, max_delay=10.0, backoff_factor=2.0
    )
    task = Task(
        execution_id=uuid4(),
        name="Curl endpoint",
        description="",
        task_type=TaskType.SHELL,
        retry_count=1,
        max_retries=3,
    )
    
    # "connection timeout" should be classified as transient
    decision = await controller.decide(task, "HTTP connection timeout occurred")
    assert decision.should_retry is True
    assert decision.delay_seconds == 2.0  # 1.0 * (2.0 ** 1)
    assert decision.failure_type == FailureType.TRANSIENT


@pytest.mark.asyncio
async def test_retry_controller_decision_permanent() -> None:
    controller = CircuitBreakerRetryController()
    task = Task(
        execution_id=uuid4(),
        name="Run script",
        description="",
        task_type=TaskType.SHELL,
        retry_count=0,
        max_retries=3,
    )
    
    # Syntax error is permanent
    decision = await controller.decide(task, "SyntaxError: invalid syntax (script.py, line 5)")
    assert decision.should_retry is False
    assert decision.failure_type == FailureType.PERMANENT
