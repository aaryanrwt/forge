# Contributing to Forge

Thank you for your interest in contributing to Forge! We welcome contributions of all kinds — from bug fixes to new executors to documentation improvements.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Fork and Clone](#fork-and-clone)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Commit Message Format](#commit-message-format)
- [Pull Request Checklist](#pull-request-checklist)
- [How to Add a New Executor](#how-to-add-a-new-executor)
- [How to Add a New LLM Provider](#how-to-add-a-new-llm-provider)
- [How to Create a Plugin](#how-to-create-a-plugin)
- [Reporting Issues](#reporting-issues)
- [Feature Requests](#feature-requests)
- [Code of Conduct](#code-of-conduct)

---

## Prerequisites

| Tool | Version | Required |
|---|---|---|
| Python | 3.11+ | ✅ Yes |
| Git | Any | ✅ Yes |
| Ollama | Latest | ❌ Optional (for LLM tests) |
| Docker | 24+ | ❌ Optional (for container tests) |
| make | Any | ❌ Optional (convenience only) |

Install Python 3.11+ from [python.org](https://python.org) or via your system package manager.

---

## Fork and Clone

```bash
# 1. Fork the repository on GitHub (click the Fork button)

# 2. Clone your fork
git clone https://github.com/<your-username>/forge.git
cd forge

# 3. Add upstream remote
git remote add upstream https://github.com/your-org/forge.git

# 4. Verify remotes
git remote -v
```

---

## Development Setup

```bash
# Install backend with all dev dependencies
make install-dev

# Or manually
cd packages/backend
pip install -e ".[dev]"
```

This installs:
- `forge` package in editable mode
- `pytest`, `pytest-asyncio`, `pytest-cov` — testing
- `ruff` — linting and formatting
- `mypy` — type checking
- `httpx` — async HTTP client (for tests)
- `pytest-watch` — test file watcher

### Environment Setup

Copy the example env file and configure it:

```bash
cp .env.example .env
```

For local development with Ollama (no API keys needed):

```bash
# .env
FORGE_LLM_PROVIDER=ollama
FORGE_OLLAMA_BASE_URL=http://localhost:11434
FORGE_LLM_MODEL=llama3.2
FORGE_LOG_LEVEL=DEBUG
```

Start the dev server:

```bash
make dev
# FastAPI running at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

---

## Running Tests

```bash
# All tests
make test

# Unit tests only (fast, no external deps)
make test-unit

# Integration tests (may require Ollama)
make test-integration

# With coverage report
make coverage

# Watch mode (auto-rerun on file change)
make test-watch
```

Tests are organized as:

```
packages/backend/tests/
├── unit/
│   ├── test_orchestrator.py
│   ├── test_planners.py
│   ├── test_executors.py
│   ├── test_verifiers.py
│   ├── test_retry.py
│   └── test_context_optimizer.py
└── integration/
    ├── test_api_executions.py
    ├── test_api_logs.py
    └── test_full_execution.py
```

---

## Code Style

Forge uses **ruff** for linting and formatting, and **mypy** for type checking.

```bash
# Check linting
make lint

# Auto-format
make format

# Type check
make typecheck

# Run all quality checks at once
make check
```

### Key Style Rules

- **Type hints required** on all public functions and methods
- **Docstrings** on all public classes and methods
- **No `Any` types** without a `# type: ignore` comment explaining why
- **Async** — all I/O operations must be `async`/`await`
- **Pydantic models** for all data transfer objects

### ruff Configuration

See `packages/backend/pyproject.toml` for full ruff configuration. Key rules enabled:
- `E`, `W` — pycodestyle
- `F` — pyflakes
- `I` — isort (import sorting)
- `N` — pep8-naming
- `UP` — pyupgrade
- `B` — flake8-bugbear
- `C4` — flake8-comprehensions

---

## Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

### Types

| Type | When to Use |
|---|---|
| `feat` | New feature or executor |
| `fix` | Bug fix |
| `docs` | Documentation only changes |
| `test` | Adding or updating tests |
| `refactor` | Code restructuring (no behavior change) |
| `perf` | Performance improvement |
| `chore` | Build system, dependency updates |
| `ci` | CI/CD changes |

### Examples

```
feat(executor): add HTTP executor for REST API calls
fix(retry): prevent infinite loop when max_retries=0
docs(contributing): add new LLM provider guide
test(orchestrator): add unit tests for circuit breaker logic
refactor(planner): extract prompt templates to constants
```

---

## Pull Request Checklist

Before opening a PR, ensure:

- [ ] Tests pass locally: `make test`
- [ ] All quality checks pass: `make check`
- [ ] New code has type hints
- [ ] New public functions have docstrings
- [ ] New features have tests
- [ ] `CHANGELOG.md` updated (if applicable)
- [ ] PR description explains **what** and **why** (not just what the code does)
- [ ] PR is against the `develop` branch (not `main`)

---

## How to Add a New Executor

Forge's executor system is designed for easy extension. Here's how to add a new one in 5 steps:

### Step 1: Define the TaskType (if needed)

```python
# packages/backend/src/forge/core/domain/models.py

class TaskType(str, Enum):
    CLI = "cli"
    SHELL = "shell"
    PYTHON = "python"
    GIT = "git"
    DOCKER = "docker"
    MCP = "mcp"
    MODEL = "model"
    HTTP = "http"  # ← Add your new type here
```

### Step 2: Implement the Executor

```python
# packages/backend/src/forge/core/application/executors/http_executor.py

from datetime import datetime, UTC
import httpx
from forge.core.domain.interfaces import IExecutor
from forge.core.domain.models import Task, TaskType, TaskStatus


class HTTPExecutor(IExecutor):
    """Execute HTTP requests as Forge tasks."""

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.HTTP

    async def execute(self, task: Task) -> Task:
        """Execute an HTTP request.

        Expected inputs:
            method: str — HTTP method (GET, POST, PUT, DELETE)
            url: str — Target URL
            headers: dict — Optional request headers
            body: dict — Optional request body (JSON)
        """
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(UTC)

        try:
            method = task.inputs.get("method", "GET").upper()
            url = task.inputs["url"]
            headers = task.inputs.get("headers", {})
            body = task.inputs.get("body")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()

            task.status = TaskStatus.COMPLETED
            task.outputs = {
                "status_code": response.status_code,
                "body": response.text,
                "headers": dict(response.headers),
            }

        except httpx.HTTPStatusError as e:
            task.status = TaskStatus.FAILED
            task.error = f"HTTP {e.response.status_code}: {e.response.text}"
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        finally:
            task.completed_at = datetime.now(UTC)

        return task
```

### Step 3: Register in the Container

```python
# packages/backend/src/forge/infrastructure/container.py

from forge.core.application.executors.http_executor import HTTPExecutor

class Container:
    def __init__(self, settings: ForgeSettings):
        # ...
        self.executor_service = ExecutorService(
            executors=[
                CLIExecutor(),
                ShellExecutor(),
                PythonExecutor(),
                GitExecutor(),
                DockerExecutor(settings),
                MCPExecutor(settings),
                ModelExecutor(self.llm_provider),
                HTTPExecutor(),  # ← Register your executor here
            ]
        )
```

### Step 4: Write Tests

```python
# packages/backend/tests/unit/test_http_executor.py

import pytest
from unittest.mock import AsyncMock, patch
from forge.core.application.executors.http_executor import HTTPExecutor
from forge.core.domain.models import Task, TaskType


@pytest.mark.asyncio
async def test_http_get_success():
    executor = HTTPExecutor()
    task = Task(
        execution_id=uuid4(),
        name="Fetch URL",
        task_type=TaskType.HTTP,
        inputs={"method": "GET", "url": "https://httpbin.org/get"},
    )

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = '{"url": "https://httpbin.org/get"}'
        mock_response.headers = {}
        mock_client.return_value.__aenter__.return_value.request = AsyncMock(
            return_value=mock_response
        )

        result = await executor.execute(task)

    assert result.status == TaskStatus.COMPLETED
    assert result.outputs["status_code"] == 200
```

### Step 5: Update Documentation

Add the new executor to:
- `README.md` executor types table
- `docs/ARCHITECTURE.md` component responsibilities table
- Add a usage example in the PR description

---

## How to Add a New LLM Provider

### Step 1: Implement BaseLLMProvider

```python
# packages/backend/src/forge/infrastructure/llm/my_provider.py

from forge.infrastructure.llm.base import BaseLLMProvider, LLMResponse
from forge.core.domain.models import TokenUsage


class MyLLMProvider(BaseLLMProvider):
    """My custom LLM provider."""

    def __init__(self, api_key: str, model: str = "my-model-v1"):
        self.api_key = api_key
        self.model = model

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        # Call your LLM API
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.myprovider.com/v1/complete",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": system_prompt,
                    "max_tokens": max_tokens,
                },
            )
            data = response.json()

        return LLMResponse(
            content=data["text"],
            prompt_tokens=data["usage"]["input_tokens"],
            completion_tokens=data["usage"]["output_tokens"],
        )

    async def is_available(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://api.myprovider.com/health")
                return response.status_code == 200
        except Exception:
            return False
```

### Step 2: Update ForgeSettings

```python
# packages/backend/src/forge/core/domain/config.py

class ForgeSettings(BaseSettings):
    llm_provider: Literal["ollama", "openai", "anthropic", "gemini", "myprovider"] = "ollama"
    my_provider_api_key: str = ""
```

### Step 3: Add to Factory

```python
# packages/backend/src/forge/infrastructure/llm/factory.py

def create_llm_provider(settings: ForgeSettings) -> BaseLLMProvider:
    match settings.llm_provider:
        case "ollama":
            return OllamaAdapter(base_url=settings.ollama_base_url, model=settings.llm_model)
        case "openai":
            return OpenAIAdapter(api_key=settings.openai_api_key, model=settings.llm_model)
        case "anthropic":
            return AnthropicAdapter(api_key=settings.anthropic_api_key, model=settings.llm_model)
        case "gemini":
            return GeminiAdapter(api_key=settings.gemini_api_key, model=settings.llm_model)
        case "myprovider":  # ← Add this case
            return MyLLMProvider(api_key=settings.my_provider_api_key, model=settings.llm_model)
        case _:
            raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
```

### Step 4: Update Documentation

Update the LLM providers table in `README.md` and this file.

---

## How to Create a Plugin

See the complete **[Plugin SDK Guide](PLUGINS.md)** for a full walkthrough.

Quick summary:

```bash
# Scaffold a plugin
forge plugin create my-awesome-plugin
cd my-awesome-plugin

# Implement IPlugin in plugin.py
# ...

# Test it
python -c "import asyncio; from plugin import Plugin; print(Plugin().name)"

# Install
forge plugin install .

# Verify
forge plugin list
```

---

## Reporting Issues

Found a bug? Please open a GitHub Issue with the following template:

```
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Run `forge run "..."`
2. See error

**Expected behavior**
What you expected to happen.

**Environment**
- OS: [e.g. macOS 14.0, Ubuntu 22.04, Windows 11]
- Python version: [e.g. 3.11.6]
- Forge version: [e.g. 1.0.0]
- LLM Provider: [e.g. ollama with llama3.2]

**Logs**
Paste relevant log output (use `forge logs <id>` to retrieve them).

**Additional context**
Any other context about the problem.
```

---

## Feature Requests

We love hearing ideas! Before opening a feature request:

1. Check the [Roadmap](ROADMAP.md) — it may already be planned
2. Search existing GitHub Issues for similar requests
3. Open a Discussion (not an Issue) to gauge community interest first

In your feature request, include:
- **Use case** — What problem does this solve?
- **Proposed API** — How would users interact with this feature?
- **Alternatives** — Have you considered other approaches?

---

## Code of Conduct

Forge follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

In short:
- **Be respectful** — No harassment, discrimination, or personal attacks
- **Be collaborative** — We're all here to build something great
- **Be patient** — Maintainers are volunteers; reviews take time
- **Be constructive** — Critique code, not people

Violations can be reported to the maintainers via email (see repository contact info).

---

Thank you for contributing to Forge! 🔥
