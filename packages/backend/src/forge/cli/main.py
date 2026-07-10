"""Forge CLI — natural language task execution engine.

Typer-based command line interface providing goal running, execution resuming,
log streaming, configuration displaying, and plugin scaffolding/management.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Core/DI
from forge.core.config import get_settings, reset_settings
from forge.core.container import Container
from forge.core.domain.models import Task, TaskStatus, TokenUsage
from forge.core.domain.events import (
    ExecutionCompletedEvent,
    ExecutionStartedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskRetriedEvent,
    TaskStartedEvent,
    VerificationCompletedEvent,
)

# CLI UI Components
from forge.cli.ui.execution_tree import render_execution_tree
from forge.cli.ui.live_panel import render_live_panel
from forge.cli.ui.token_meter import render_token_meter

app = typer.Typer(name="forge", help="Forge: The AI Execution Layer")
plugin_app = typer.Typer(name="plugin", help="Manage Forge plugins")
app.add_typer(plugin_app)

console = Console()


async def _init_container() -> Container:
    """Helper to instantiate and startup the DI container."""
    container = Container()
    await container.initialize()
    return container


# ── CLI Commands ─────────────────────────────────────────────────────────────

@app.command()
def init() -> None:
    """Initialize the Forge workspace, creating settings and database."""
    console.print("[bold green]Initializing Forge Workspace...[/bold green]")
    settings = get_settings()
    
    # Initialize DB (which creates SQLite file and tables)
    async def _init_db() -> None:
        container = Container(settings)
        await container.initialize()
        await container.close()

    try:
        asyncio.run(_init_db())
        console.print(f"[bold green][OK][/bold green] Database initialized at: [cyan]{settings.db_url}[/cyan]")
        console.print(f"[bold green][OK][/bold green] Plugins directory configured: [cyan]{settings.plugins_dir}[/cyan]")
        console.print("[bold green]Forge is ready to run! Use: [cyan]forge run \"your goal\"[/cyan][/bold green]")
    except Exception as exc:
        console.print(f"[bold red]Initialization failed:[/bold red] {exc}", style="red")
        raise typer.Exit(1)


@app.command()
def run(
    goal: str = typer.Argument(..., help="The natural-language goal for Forge to execute"),
) -> None:
    """Plan, execute, and verify a multi-step goal in real time."""
    async def _run() -> None:
        container = await _init_container()
        
        # We will poll/monitor the execution by querying the database in our live loop.
        # This decouples UI rendering from direct callbacks and handles updates cleanly.
        console.print("[bold cyan]Submitting goal to Forge planner...[/bold cyan]")
        try:
            execution = await container.orchestrator.planner.plan(goal)
            # Save initially planned tasks
            await container.memory_repo.save_execution(execution)
            for t in execution.tasks:
                await container.memory_repo.save_task(t)
        except Exception as exc:
            console.print(f"[bold red]Planning failed:[/bold red] {exc}")
            await container.close()
            raise typer.Exit(1)

        console.print(f"Plan generated with {len(execution.tasks)} steps.")
        
        # Start execution in background
        exec_task = asyncio.create_task(container.orchestrator._run_execution(execution))
        
        start_time = time.time()
        
        with Live(render_live_panel(goal, "pending", execution.tasks), refresh_per_second=4) as live:
            while not exec_task.done():
                await asyncio.sleep(0.25)
                # Fetch fresh status from repo
                latest_exec = await container.memory_repo.get_execution(execution.id)
                if latest_exec:
                    live.update(
                        render_live_panel(
                            goal=goal,
                            status=latest_exec.status.value,
                            tasks=latest_exec.tasks,
                            elapsed_seconds=time.time() - start_time,
                        )
                    )
            
            # Wait for execution task to fully resolve
            final_execution = await exec_task

            # Final render
            live.update(
                render_live_panel(
                    goal=goal,
                    status=final_execution.status.value,
                    tasks=final_execution.tasks,
                    elapsed_seconds=time.time() - start_time,
                )
            )

        console.print("\n[bold green]Goal execution run completed.[/bold green]")
        
        # Print token usage
        if final_execution.token_usage.total_tokens > 0:
            console.print(render_token_meter(final_execution.token_usage))
            
        if final_execution.status == TaskStatus.FAILED:
            console.print(f"[bold red]Execution failed:[/bold red] {final_execution.error}")
            await container.close()
            raise typer.Exit(1)

        await container.close()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Execution interrupted by user.[/yellow]")
        raise typer.Exit(130)


@app.command()
def resume(
    execution_id: UUID = typer.Argument(..., help="The UUID of the execution to resume"),
) -> None:
    """Resume a failed or halted execution run from where it stopped."""
    async def _resume() -> None:
        container = await _init_container()
        
        # Verify execution exists
        execution = await container.memory_repo.get_execution(execution_id)
        if not execution:
            console.print(f"[bold red]Execution {execution_id} not found.[/bold red]")
            await container.close()
            raise typer.Exit(1)

        console.print(f"[bold cyan]Resuming goal: {execution.goal}[/bold cyan]")
        
        # Start resume in background
        exec_task = asyncio.create_task(container.orchestrator.resume(execution_id))
        start_time = time.time()
        
        with Live(render_live_panel(execution.goal, "in_progress", execution.tasks), refresh_per_second=4) as live:
            while not exec_task.done():
                await asyncio.sleep(0.25)
                latest_exec = await container.memory_repo.get_execution(execution_id)
                if latest_exec:
                    live.update(
                        render_live_panel(
                            goal=execution.goal,
                            status=latest_exec.status.value,
                            tasks=latest_exec.tasks,
                            elapsed_seconds=time.time() - start_time,
                        )
                    )
            
            final_execution = await exec_task
            live.update(
                render_live_panel(
                    goal=execution.goal,
                    status=final_execution.status.value,
                    tasks=final_execution.tasks,
                    elapsed_seconds=time.time() - start_time,
                )
            )

        console.print("\n[bold green]Goal execution resume completed.[/bold green]")
        if final_execution.status == TaskStatus.FAILED:
            console.print(f"[bold red]Execution failed:[/bold red] {final_execution.error}")
            await container.close()
            raise typer.Exit(1)

        await container.close()

    try:
        asyncio.run(_resume())
    except KeyboardInterrupt:
        console.print("\n[yellow]Execution interrupted by user.[/yellow]")
        raise typer.Exit(130)


@app.command()
def status(
    execution_id: UUID = typer.Argument(..., help="The UUID of the execution"),
) -> None:
    """Display the task graph and status of a specific execution."""
    async def _status() -> None:
        container = await _init_container()
        execution = await container.memory_repo.get_execution(execution_id)
        if not execution:
            console.print(f"[bold red]Execution {execution_id} not found.[/bold red]")
            await container.close()
            raise typer.Exit(1)

        # Print tree visualization
        tree = render_execution_tree(execution.tasks, title=f"Goal: {execution.goal}")
        console.print(tree)
        console.print(f"\n[bold]Overall Status:[/bold] {execution.status.value.upper()}")
        if execution.error:
            console.print(f"[bold red]Error:[/bold red] {execution.error}")
            
        await container.close()

    asyncio.run(_status())


@app.command()
def logs(
    execution_id: UUID = typer.Argument(..., help="The UUID of the execution"),
    limit: int = typer.Option(100, help="Max log entries to fetch"),
) -> None:
    """Display all structured logs for a specific execution."""
    async def _logs() -> None:
        container = await _init_container()
        logs_list = await container.memory_repo.get_logs(execution_id, limit=limit)
        if not logs_list:
            console.print(f"[yellow]No logs found for execution {execution_id}.[/yellow]")
            await container.close()
            return

        table = Table(title=f"Logs for execution {execution_id}", box=None)
        table.add_column("Timestamp", style="dim")
        table.add_column("Level", style="bold")
        table.add_column("Message")
        
        for entry in logs_list:
            level_color = "red" if entry.level.value == "error" else "yellow" if entry.level.value == "warning" else "white"
            table.add_row(
                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                f"[{entry.level.value.upper()}]",
                entry.message,
                style=level_color,
            )
        console.print(table)
        await container.close()

    asyncio.run(_logs())


@app.command()
def explain(
    execution_id: UUID = typer.Argument(..., help="The UUID of the execution to summarize/explain"),
) -> None:
    """Print an AI-generated or structured summary of an execution run."""
    async def _explain() -> None:
        container = await _init_container()
        execution = await container.memory_repo.get_execution(execution_id)
        if not execution:
            console.print(f"[bold red]Execution {execution_id} not found.[/bold red]")
            await container.close()
            raise typer.Exit(1)

        summary_text = await container.memory_service.summarize_execution(execution_id)
        console.print(Panel(summary_text, title=f"Explanation: {execution_id}", border_style="cyan"))
        await container.close()

    asyncio.run(_explain())


@app.command()
def replay(
    task_id: UUID = typer.Argument(..., help="The UUID of the task to view"),
) -> None:
    """Examine the detailed inputs and outputs of a specific task."""
    async def _replay() -> None:
        container = await _init_container()
        task = await container.memory_repo.get_task(task_id)
        if not task:
            console.print(f"[bold red]Task {task_id} not found.[/bold red]")
            await container.close()
            raise typer.Exit(1)

        console.print(f"[bold cyan]Task Name:[/bold cyan] {task.name}")
        console.print(f"[bold cyan]Type:[/bold cyan] {task.task_type.value}")
        console.print(f"[bold cyan]Status:[/bold cyan] {task.status.value.upper()}")
        
        import pprint
        console.print("\n[bold green]Inputs:[/bold green]")
        console.print(pprint.pformat(task.inputs))
        
        console.print("\n[bold green]Outputs:[/bold green]")
        console.print(pprint.pformat(task.outputs))
        
        if task.error:
            console.print(f"\n[bold red]Error:[/bold red] {task.error}")
            
        await container.close()

    asyncio.run(_replay())


@app.command()
def config() -> None:
    """Print the active runtime configurations of the Forge engine."""
    settings = get_settings()
    console.print(Panel(
        f"[bold]Database URL:[/bold]          {settings.db_url}\n"
        f"[bold]LLM Provider:[/bold]          {settings.llm_provider}\n"
        f"[bold]LLM Model:[/bold]             {settings.llm_model}\n"
        f"[bold]Planner Type:[/bold]          {settings.planner_type}\n"
        f"[bold]Executor Timeout:[/bold]      {settings.executor_timeout}s\n"
        f"[bold]Max Retries/Task:[/bold]      {settings.default_max_retries}\n"
        f"[bold]Circuit Threshold:[/bold]     {settings.circuit_breaker_threshold}\n"
        f"[bold]Circuit Timeout:[/bold]       {settings.circuit_breaker_timeout}s\n"
        f"[bold]Context Window:[/bold]        {settings.context_window_size} messages\n"
        f"[bold]Plugins Dir:[/bold]           {settings.plugins_dir}\n"
        f"[bold]Log Level:[/bold]             {settings.log_level}",
        title="Forge Configurations",
        border_style="magenta",
    ))


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Attempt to auto-repair minor configuration issues"),
    system: bool = typer.Option(False, "--system", help="Print detailed system core stats"),
) -> None:
    """Run diagnostics to verify system health, config, DB and LLM integrations."""
    import platform
    import shutil
    
    console.print("[bold cyan]Forge Diagnostic Checkup[/bold cyan]\n")
    
    # 1. System stats
    if system:
        console.print("[bold green]System Info:[/bold green]")
        console.print(f"  OS Platform: {platform.system()} {platform.release()} ({platform.machine()})")
        console.print(f"  Python:      {sys.version.split()[0]}")
        try:
            import psutil
            mem = psutil.virtual_memory()
            console.print(f"  CPU Cores:   {psutil.cpu_count()}")
            console.print(f"  RAM Total:   {mem.total / (1024**3):.2f} GB")
        except ImportError:
            console.print("  CPU Cores:   (Install psutil for CPU/RAM metrics)")
        console.print("")

    # 2. Config & DB connection
    settings = get_settings()
    console.print("[bold green]Database & Config:[/bold green]")
    console.print(f"  URL:  {settings.db_url}")
    
    db_ok = False
    try:
        async def check_db():
            container = Container()
            await container.initialize()
            # Test write
            from uuid import uuid4
            from forge.core.domain.models import Execution, TaskStatus
            test_exec = Execution(id=uuid4(), goal="Doctor test goal", status=TaskStatus.PENDING)
            await container.memory_repo.save_execution(test_exec)
            fetched = await container.memory_repo.get_execution(test_exec.id)
            await container.close()
            return fetched is not None
        db_ok = asyncio.run(check_db())
        console.print("  State: [bold green]Connected & Writeable[/bold green]")
    except Exception as exc:
        console.print(f"  State: [bold red]Database Error:[/bold red] {exc}")
        if fix:
            console.print("  [yellow]Attempting DB migration/repair...[/yellow]")
            try:
                async def run_init():
                    c = Container()
                    await c.memory_repo.init_db()
                    await c.close()
                asyncio.run(run_init())
                console.print("  State: [bold green]Initialized Successfully[/bold green]")
            except Exception as e:
                console.print(f"  [bold red]Repair failed:[/bold red] {e}")

    # 3. LLM check
    console.print("\n[bold green]LLM Provider Connectivity:[/bold green]")
    console.print(f"  Provider: {settings.llm_provider} ({settings.llm_model})")
    try:
        async def check_llm():
            container = Container()
            if container.llm_provider:
                avail = await container.llm_provider.is_available()
                await container.close()
                return avail
            await container.close()
            return False
        llm_avail = asyncio.run(check_llm())
        if llm_avail:
            console.print("  State:    [bold green]Online & Reachable[/bold green]")
        else:
            console.print("  State:    [yellow]Offline or Not Reachable (Ollama requires local running instance)[/yellow]")
    except Exception as exc:
        console.print(f"  State:    [bold red]LLM Config Error:[/bold red] {exc}")

    # 4. Binaries check
    console.print("\n[bold green]Path Executables:[/bold green]")
    for binary in ["git", "docker"]:
        bin_path = shutil.which(binary)
        if bin_path:
            console.print(f"  {binary}: [bold green]Found[/bold green] at {bin_path}")
        else:
            console.print(f"  {binary}: [yellow]Not Found on PATH[/yellow] (related executors will fail)")

    # 5. Directory checks
    console.print("\n[bold green]Plugins Sandbox:[/bold green]")
    plugins_path = Path(settings.plugins_dir)
    console.print(f"  Path: {plugins_path}")
    if plugins_path.exists():
        console.print("  State: [bold green]Directory Exists[/bold green]")
    else:
        console.print("  State: [yellow]Directory Missing[/yellow]")
        if fix:
            try:
                plugins_path.mkdir(parents=True, exist_ok=True)
                console.print("  State: [bold green]Directory Created[/bold green]")
            except Exception as e:
                console.print(f"  [bold red]Failed to create dir:[/bold red] {e}")


@app.command()
def trace(
    execution_id: UUID = typer.Argument(..., help="The UUID of the execution run to trace"),
) -> None:
    """Print ASCII telemetry span timeline showing execution latency breakdowns."""
    async def _trace() -> None:
        container = await _init_container()
        execution = await container.memory_repo.get_execution(execution_id)
        if not execution:
            console.print(f"[bold red]Execution {execution_id} not found.[/bold red]")
            await container.close()
            raise typer.Exit(1)

        telemetry = execution.metadata.get("telemetry", {})
        spans = telemetry.get("spans", [])
        if not spans:
            console.print("[yellow]No telemetry trace spans recorded for this execution run.[/yellow]")
            await container.close()
            return

        console.print(f"[bold cyan]Performance Trace Timeline for Goal:[/bold cyan] {execution.goal}\n")

        # Find maximum span duration to scale the bar
        max_duration = max(span["duration_ms"] for span in spans) if spans else 1.0

        table = Table(title="Spans breakdown", box=None)
        table.add_column("Span Name", width=15, style="magenta")
        table.add_column("Duration (ms)", width=15, justify="right", style="green")
        table.add_column("Timeline Bar")

        for idx, span in enumerate(spans):
            dur = span["duration_ms"]
            # Scale bar length (max 30 chars)
            bar_len = int((dur / max_duration) * 30) if max_duration > 0 else 0
            bar = "█" * bar_len + "░" * (30 - bar_len)
            table.add_row(
                span["span"],
                f"{dur:.2f} ms",
                f"[{bar}]"
            )
        
        console.print(table)
        
        # Print metrics summaries
        metrics = telemetry.get("metrics", {})
        if metrics:
            console.print("\n[bold green]Metrics Summary:[/bold green]")
            for k, v in metrics.items():
                console.print(f"  {k:<20}: {v:.2f} ms")
        
        await container.close()

    asyncio.run(_trace())


@app.command()
def inspect(
    execution_id: UUID = typer.Argument(..., help="The UUID of the execution to inspect"),
) -> None:
    """Print detailed execution details and telemetry metrics in JSON format."""
    async def _inspect() -> None:
        container = await _init_container()
        execution = await container.memory_repo.get_execution(execution_id)
        if not execution:
            console.print(f"[bold red]Execution {execution_id} not found.[/bold red]")
            await container.close()
            raise typer.Exit(1)

        json_data = execution.model_dump_json(indent=2)
        console.print_json(json_data)
        await container.close()

    asyncio.run(_inspect())


@app.command()
def graph(
    execution_id: UUID = typer.Argument(..., help="The UUID of the execution"),
) -> None:
    """Print ASCII task dependency graph flow for the goal."""
    async def _graph() -> None:
        container = await _init_container()
        execution = await container.memory_repo.get_execution(execution_id)
        if not execution:
            console.print(f"[bold red]Execution {execution_id} not found.[/bold red]")
            await container.close()
            raise typer.Exit(1)

        console.print(f"[bold cyan]Task Graph for Goal:[/bold cyan] {execution.goal}\n")
        console.print("  [Start]")
        
        sorted_tasks = sorted(execution.tasks, key=lambda t: t.order_index)
        for t in sorted_tasks:
            status_colors = {
                TaskStatus.COMPLETED: "green",
                TaskStatus.FAILED: "red",
                TaskStatus.PENDING: "yellow",
                TaskStatus.IN_PROGRESS: "blue",
            }
            color = status_colors.get(t.status, "white")
            
            console.print("     │")
            console.print("     ▼")
            console.print(f"  [Task {t.order_index}] [bold]{t.name}[/bold] ({t.task_type.value}) -> [{color}]{t.status.value}[/{color}]")
            if t.dependencies:
                dep_indices = []
                for dep_id in t.dependencies:
                    dep_task = next((x for x in sorted_tasks if x.id == dep_id), None)
                    if dep_task:
                        dep_indices.append(str(dep_task.order_index))
                console.print(f"       (Depends on Tasks: {', '.join(dep_indices)})")
        
        console.print("     │")
        console.print("     ▼")
        console.print("  [Finish]")
        await container.close()

    asyncio.run(_graph())


@app.command()
def benchmark() -> None:
    """Run local engine performance overhead benchmark tests."""
    console.print("[bold green]Starting Forge Overhead Performance Benchmarks...[/bold green]")
    try:
        from benchmarks.report import run_benchmarks_and_check
        run_benchmarks_and_check()
    except Exception as exc:
        console.print(f"[bold red]Benchmark run encountered an error:[/bold red] {exc}")
        raise typer.Exit(1)


# ── Plugin Subgroup Commands ──────────────────────────────────────────────────

@plugin_app.command("list")
def list_plugins() -> None:
    """List all installed and discovered plugins."""
    async def _list() -> None:
        container = await _init_container()
        plugins = container.plugin_manager.list_plugins()
        if not plugins:
            console.print("[yellow]No plugins installed.[/yellow]")
            await container.close()
            return

        table = Table(title="Installed Plugins")
        table.add_column("Name", style="cyan")
        table.add_column("Version", style="magenta")
        table.add_column("Task Type", style="green")
        table.add_column("Description")
        
        for p in plugins:
            table.add_row(p.name, p.version, p.task_type, p.description)
            
        console.print(table)
        await container.close()

    asyncio.run(_list())


@plugin_app.command("install")
def install_plugin(
    path: Path = typer.Argument(..., help="Path to local plugin directory containing forge_plugin.json"),
) -> None:
    """Install a plugin from a local source directory path."""
    async def _install() -> None:
        container = await _init_container()
        try:
            manifest = await container.plugin_manager.install_plugin(path)
            console.print(f"[bold green]Successfully installed plugin: {manifest.name} v{manifest.version}[/bold green]")
        except Exception as exc:
            console.print(f"[bold red]Plugin installation failed:[/bold red] {exc}")
            await container.close()
            raise typer.Exit(1)
        await container.close()

    asyncio.run(_install())


@plugin_app.command("create")
def create_plugin(
    name: str = typer.Argument(..., help="Name of the new plugin to scaffold"),
    output_dir: Path = typer.Option(Path("."), help="Where to scaffold the new plugin directory"),
) -> None:
    """Scaffold a template directory structure for a new plugin."""
    try:
        from forge.application.services.plugin_manager import PluginManager
        plugin_path = PluginManager.scaffold_plugin(name, output_dir)
        console.print(f"[bold green]Scaffolded plugin '{name}' template at: [cyan]{plugin_path}[/cyan][/bold green]")
    except Exception as exc:
        console.print(f"[bold red]Plugin scaffolding failed:[/bold red] {exc}")
        raise typer.Exit(1)


# Main Entrypoint
def main() -> None:
    app()


if __name__ == "__main__":
    main()
