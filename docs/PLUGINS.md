# Forge Plugin SDK

Plugins extend Forge with custom executor types. A plugin is a Python package that implements the `IPlugin` interface.

## Quick Start

```bash
# Scaffold a new plugin
forge plugin create my-slack-notifier

# Edit the plugin
cd my-slack-notifier
# ... implement your logic ...

# Install it
forge plugin install ./my-slack-notifier

# Verify
forge plugin list
```

## Plugin Anatomy

```
my-plugin/
├── forge_plugin.json    # Plugin manifest
├── plugin.py           # Plugin implementation
└── README.md           # Plugin documentation
```

## forge_plugin.json

```json
{
  "name": "my-slack-notifier",
  "version": "1.0.0",
  "description": "Send Slack notifications as Forge tasks",
  "author": "Your Name",
  "task_type": "cli",
  "entry_point": "plugin.py"
}
```

## plugin.py — Implementing IPlugin

```python
from datetime import datetime
from forge.core.domain.interfaces import IPlugin
from forge.core.domain.models import Task, TaskType, TaskStatus


class Plugin(IPlugin):
    """Slack notification plugin for Forge."""

    @property
    def name(self) -> str:
        return "my-slack-notifier"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Send messages to Slack"

    @property
    def task_type(self) -> TaskType:
        return TaskType.CLI  # Use an existing TaskType

    def supports(self, task_type: TaskType) -> bool:
        return task_type == self.task_type

    async def execute(self, task: Task) -> Task:
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()

        try:
            webhook_url = task.inputs.get("webhook_url", "")
            message = task.inputs.get("message", task.description)

            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"text": message}
                )
                response.raise_for_status()

            task.status = TaskStatus.COMPLETED
            task.outputs = {"status": "sent", "message": message}

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        finally:
            task.completed_at = datetime.utcnow()

        return task
```

## Using Your Plugin in a Task

When your plugin is installed, you can reference its task_type in executions:

```python
# Via API
import httpx

response = httpx.post("http://localhost:8000/api/v1/executions", json={
    "goal": "Notify team on Slack"
})
```

Or directly create a task with matching inputs:
```json
{
  "task_type": "cli",
  "name": "Slack notification",
  "inputs": {
    "webhook_url": "https://hooks.slack.com/...",
    "message": "Deployment complete!"
  }
}
```

## IPlugin Interface Reference

```python
class IPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def task_type(self) -> TaskType: ...

    @abstractmethod
    def supports(self, task_type: TaskType) -> bool: ...

    @abstractmethod
    async def execute(self, task: Task) -> Task: ...
```

## Plugin Storage

Plugins are stored in `~/.forge/plugins/`. Each plugin must be in its own subdirectory:

```
~/.forge/plugins/
├── my-slack-notifier/
│   ├── forge_plugin.json
│   └── plugin.py
└── my-github-reporter/
    ├── forge_plugin.json
    └── plugin.py
```

## Plugin Manifest Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Unique plugin identifier (kebab-case) |
| `version` | string | ✅ | SemVer version string |
| `description` | string | ✅ | Short description |
| `author` | string | ❌ | Plugin author name |
| `task_type` | string | ✅ | Which `TaskType` this plugin handles |
| `entry_point` | string | ✅ | Python file containing the `Plugin` class |
| `requires` | list | ❌ | pip package dependencies |

### Manifest with Dependencies

```json
{
  "name": "my-slack-notifier",
  "version": "1.0.0",
  "description": "Send Slack notifications as Forge tasks",
  "author": "Your Name <you@example.com>",
  "task_type": "cli",
  "entry_point": "plugin.py",
  "requires": ["httpx>=0.27.0", "slack-sdk>=3.0.0"]
}
```

## Example Plugins

### 1. File Writer Plugin

Write content to a file as a Forge task:

```python
import aiofiles
from datetime import datetime
from forge.core.domain.interfaces import IPlugin
from forge.core.domain.models import Task, TaskType, TaskStatus


class Plugin(IPlugin):
    @property
    def name(self) -> str:
        return "file-writer"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Write content to files"

    @property
    def task_type(self) -> TaskType:
        return TaskType.PYTHON

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.PYTHON

    async def execute(self, task: Task) -> Task:
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()

        try:
            path = task.inputs["path"]
            content = task.inputs["content"]
            mode = task.inputs.get("mode", "w")

            async with aiofiles.open(path, mode=mode) as f:
                await f.write(content)

            task.status = TaskStatus.COMPLETED
            task.outputs = {"path": path, "bytes_written": len(content)}

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        finally:
            task.completed_at = datetime.utcnow()

        return task
```

### 2. Webhook Notifier Plugin

Call a generic webhook on task completion:

```python
import httpx
from datetime import datetime
from forge.core.domain.interfaces import IPlugin
from forge.core.domain.models import Task, TaskType, TaskStatus


class Plugin(IPlugin):
    @property
    def name(self) -> str:
        return "webhook-notifier"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "POST to a webhook URL with task data"

    @property
    def task_type(self) -> TaskType:
        return TaskType.MODEL

    def supports(self, task_type: TaskType) -> bool:
        return task_type == TaskType.MODEL

    async def execute(self, task: Task) -> Task:
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()

        try:
            url = task.inputs["url"]
            payload = task.inputs.get("payload", {})
            headers = task.inputs.get("headers", {"Content-Type": "application/json"})

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

            task.status = TaskStatus.COMPLETED
            task.outputs = {
                "status_code": response.status_code,
                "response": response.text[:500],
            }

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        finally:
            task.completed_at = datetime.utcnow()

        return task
```

## Testing Your Plugin

```python
# test_plugin.py
import asyncio
from uuid import uuid4
from forge.core.domain.models import Task, TaskType
from plugin import Plugin


async def test():
    plugin = Plugin()
    print(f"Plugin: {plugin.name} v{plugin.version}")
    print(f"Supports {plugin.task_type}: {plugin.supports(plugin.task_type)}")

    task = Task(
        execution_id=uuid4(),
        name="Test task",
        description="Test task description",
        task_type=plugin.task_type,
        inputs={
            "webhook_url": "https://httpbin.org/post",
            "message": "Hello from Forge!"
        }
    )

    result = await plugin.execute(task)
    print(f"Status: {result.status}")
    print(f"Outputs: {result.outputs}")
    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(test())
```

Run with:
```bash
python test_plugin.py
```

## Publishing Your Plugin

Currently, plugins are installed locally via `forge plugin install <path>`.

In **v2.0**, Forge Hub will provide a community plugin registry where you can publish your plugins for others to discover and install:

```bash
# Future v2.0 feature
forge plugin publish  # Publishes to Forge Hub
forge plugin install my-slack-notifier  # Installs from Forge Hub
```

Until then, share your plugin by:
1. Publishing it as a GitHub repository (prefix: `forge-plugin-`)
2. Adding it to the community list in the Forge discussions
3. Submitting a PR to add it to the official plugin catalog
