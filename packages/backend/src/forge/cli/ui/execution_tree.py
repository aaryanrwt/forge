"""Rich Tree renderer for displaying the task DAG in a visual tree format."""
from __future__ import annotations

from typing import List, Dict
from uuid import UUID
from rich.tree import Tree
from rich.text import Text

from forge.core.domain.models import Task, TaskStatus


def render_execution_tree(tasks: List[Task], title: str = "Execution Plan") -> Tree:
    """Construct and return a Rich Tree visual showing the execution steps and statuses.

    Builds sequential/dependent visual tree nodes.
    """
    root = Tree(f"[bold cyan]{title}[/bold cyan]")

    status_colors = {
        TaskStatus.PENDING: "yellow",
        TaskStatus.IN_PROGRESS: "bold blue",
        TaskStatus.COMPLETED: "bold green",
        TaskStatus.FAILED: "bold red",
        TaskStatus.SKIPPED: "dim white",
        TaskStatus.CANCELLED: "dim red",
    }

    # Since tasks are sequential in v1.0, we can display them in order.
    # We will draw a straight tree showing order of operations and dependencies.
    sorted_tasks = sorted(tasks, key=lambda t: t.order_index)

    for task in sorted_tasks:
        status_color = status_colors.get(task.status, "white")
        status_text = f"[{task.status.value.upper()}]"
        
        node_text = Text()
        node_text.append(f"Step {task.order_index}: ", style="bold magenta")
        node_text.append(f"{task.name} ", style="white")
        node_text.append(f"({task.task_type.value}) ", style="dim italic")
        node_text.append(status_text, style=status_color)

        node = root.add(node_text)
        
        # If there are outputs/errors, add them as sub-nodes
        if task.status == TaskStatus.FAILED and task.error:
            node.add(f"[bold red]Error:[/bold red] {task.error}")
        elif task.status == TaskStatus.COMPLETED and task.outputs:
            # Show a compact preview of outputs
            out_preview = str(task.outputs)
            if len(out_preview) > 120:
                out_preview = out_preview[:120] + "..."
            node.add(f"[dim]Outputs:[/dim] {out_preview}")

    return root
