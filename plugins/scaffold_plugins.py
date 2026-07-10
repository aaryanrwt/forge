"""Scaffold a plugins/ directory for community-contributed task plugins."""
from __future__ import annotations

import json
from pathlib import Path

PLUGINS = [
    "docker",
    "python",
    "git",
    "shell",
    "mcp",
    "filesystem",
    "github",
    "sqlite"
]


def scaffold_plugins() -> None:
    plugins_dir = Path("./plugins")
    plugins_dir.mkdir(exist_ok=True)
    
    for name in PLUGINS:
        dir_path = plugins_dir / name
        dir_path.mkdir(exist_ok=True)
        
        # Write forge_plugin.json template
        manifest = {
            "name": f"{name}-plugin",
            "version": "1.0.0",
            "description": f"Community plugin for running {name} tasks",
            "author": "Forge Open Source Community",
            "task_type": f"custom-{name}",
            "entry_point": "plugin.py"
        }
        with open(dir_path / "forge_plugin.json", "w") as f:
            json.dump(manifest, f, indent=2)
            
        # Write plugin.py template
        code = f"""\"\"\"{name.capitalize()} Plugin implementation for custom-{name} tasks.\"\"\"
from __future__ import annotations

from forge.core.domain.interfaces import IPlugin
from forge.core.domain.models import Task, TaskStatus


class {name.capitalize()}Plugin(IPlugin):
    @property
    def name(self) -> str:
        return "{name}-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Custom task execution wrapper for {name}."

    @property
    def task_type(self) -> str:
        return "custom-{name}"

    def supports(self, task_type) -> bool:
        # Check task type
        # Can compare by string or TaskType enum
        if hasattr(task_type, "value"):
            return task_type.value == self.task_type
        return str(task_type) == self.task_type

    async def execute(self, task: Task) -> Task:
        # Custom execution logic
        task.status = TaskStatus.COMPLETED
        task.outputs = {{"result": "Executed custom {name} task"}}
        return task
"""
        with open(dir_path / "plugin.py", "w") as f:
            f.write(code)
            
    print(f"Scaffolded {len(PLUGINS)} community plugin slots under /plugins!")


if __name__ == "__main__":
    scaffold_plugins()
