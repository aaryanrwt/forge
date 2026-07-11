"""Rich live dashboard panel for monitoring executions in real time."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from forge.core.domain.models import Task, TaskStatus


def render_live_panel(
    goal: str,
    status: str,
    tasks: list[Task],
    elapsed_seconds: float = 0.0,
) -> Panel:
    """Return a Panel containing a formatted status table of all tasks in the execution."""
    status_colors = {
        "pending": "yellow",
        "in_progress": "bold blue",
        "completed": "bold green",
        "failed": "bold red",
        "cancelled": "dim red",
    }

    # Header info
    status_color = status_colors.get(status, "white")
    header_text = Text()
    header_text.append("Goal: ", style="bold cyan")
    header_text.append(f"{goal}\n", style="bold white")
    header_text.append("Status: ", style="bold cyan")
    header_text.append(f"{status.upper()} ", style=status_color)
    header_text.append(f"({elapsed_seconds:.1f}s elapsed)\n", style="dim")

    # Table of tasks
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("#", width=3, justify="right")
    table.add_column("Task Name", width=30)
    table.add_column("Type", width=10)
    table.add_column("Status", width=15)
    table.add_column("Retries", width=8, justify="center")
    table.add_column("Message/Error")

    sorted_tasks = sorted(tasks, key=lambda t: t.order_index)
    for task in sorted_tasks:
        task_color = status_colors.get(task.status.value, "white")

        status_text = Text(task.status.value.upper(), style=task_color)
        if task.status == TaskStatus.IN_PROGRESS:
            status_text.append(" ↺", style="blink")

        msg = ""
        if task.error:
            msg = f"[red]{task.error}[/red]"
        elif task.status == TaskStatus.COMPLETED and task.outputs:
            if "result" in task.outputs:
                msg = str(task.outputs["result"])
            elif "stdout" in task.outputs:
                # Capture short stdout preview
                stdout = task.outputs["stdout"].strip().split("\n")
                msg = stdout[-1] if stdout else ""
            if len(msg) > 60:
                msg = msg[:57] + "..."

        table.add_row(
            str(task.order_index),
            task.name,
            task.task_type.value,
            status_text,
            f"{task.retry_count}/{task.max_retries}",
            msg,
        )

    # Combine into panel using Group container
    panel_content = Group(header_text, table)
    return Panel(
        panel_content,
        title="[bold green]Forge Execution Monitor[/bold green]",
        border_style="green",
        expand=True,
    )
