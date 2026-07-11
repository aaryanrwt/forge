"""Python Plugin implementation for custom-python tasks."""

from __future__ import annotations

from forge.core.domain.interfaces import IPlugin
from forge.core.domain.models import Task, TaskStatus


class PythonPlugin(IPlugin):
    @property
    def name(self) -> str:
        return "python-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Custom task execution wrapper for python."

    @property
    def task_type(self) -> str:
        return "custom-python"

    def supports(self, task_type) -> bool:
        # Check task type
        # Can compare by string or TaskType enum
        if hasattr(task_type, "value"):
            return task_type.value == self.task_type
        return str(task_type) == self.task_type

    async def execute(self, task: Task) -> Task:
        # Custom execution logic
        task.status = TaskStatus.COMPLETED
        task.outputs = {"result": "Executed custom python task"}
        return task
