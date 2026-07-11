"""Pytest fixtures for Forge testing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio

from forge.core.config import ForgeSettings
from forge.core.container import Container
from forge.core.domain.models import Execution, Task, TaskStatus, TaskType


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings() -> ForgeSettings:
    """Return settings configured for testing with an in-memory SQLite database."""
    return ForgeSettings(
        db_url="sqlite+aiosqlite:///:memory:",
        llm_provider="ollama",
        llm_model="llama3.2",
        planner_type="rule",
        log_level="DEBUG",
    )


@pytest_asyncio.fixture
async def test_container(test_settings: ForgeSettings) -> AsyncGenerator[Container, None]:
    """Yield an initialized Container configured with in-memory SQLite database."""
    container = Container(settings=test_settings)
    await container.initialize()
    yield container
    await container.close()


@pytest.fixture
def mock_execution() -> Execution:
    """Return a skeleton Execution model."""
    exec_id = uuid4()
    return Execution(
        id=exec_id,
        goal="Test running goal",
        status=TaskStatus.PENDING,
        tasks=[
            Task(
                id=uuid4(),
                execution_id=exec_id,
                name="Test Task 1",
                description="This is step 1",
                task_type=TaskType.SHELL,
                inputs={"command": "echo test1"},
                order_index=0,
            ),
            Task(
                id=uuid4(),
                execution_id=exec_id,
                name="Test Task 2",
                description="This is step 2",
                task_type=TaskType.PYTHON,
                inputs={"code": "result = 42"},
                order_index=1,
            ),
        ],
    )
