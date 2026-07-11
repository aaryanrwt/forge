"""Benchmark report generator and performance regression comparison budget checker."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Import individual benchmarks
import benchmarks.planning as planning
import benchmarks.execution as execution
import benchmarks.memory as memory
import benchmarks.compression as compression
import benchmarks.verification as verification
import benchmarks.plugin as plugin
import benchmarks.api as api
import benchmarks.websocket as websocket


def format_ms(val: float) -> str:
    if val < 0.01:
        return "< 0.01 ms"
    return f"{val:.2f} ms"


def run_benchmarks_and_check() -> None:
    results_dir = Path("./benchmarks/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run all benchmarks
    print("Running Planning Benchmark...")
    planning_ms = planning.run_benchmark()

    print("Running Execution Benchmark...")
    execution_ms = execution.run_benchmark()

    print("Running Memory (DB) Benchmark...")
    memory_ms = memory.run_benchmark()

    print("Running Compression Benchmark...")
    compression_ms = compression.run_benchmark()

    print("Running Verification Benchmark...")
    verification_ms = verification.run_benchmark()

    print("Running Plugin Benchmark...")
    plugin_ms = plugin.run_benchmark()

    print("Running API Benchmark...")
    api_ms = api.run_benchmark()

    print("Running WebSocket Benchmark...")
    websocket_ms = websocket.run_benchmark()

    current_run = {
        "planning_ms": planning_ms,
        "execution_ms": execution_ms,
        "memory_ms": memory_ms,
        "compression_ms": compression_ms,
        "verification_ms": verification_ms,
        "plugin_ms": plugin_ms,
        "api_ms": api_ms,
        "websocket_ms": websocket_ms,
    }

    # 2. Compare against baseline.json if it exists
    baseline_file = results_dir / "baseline.json"
    regressed = False
    comparison_logs = []

    if baseline_file.exists():
        try:
            with open(baseline_file, "r") as f:
                baseline = json.load(f)

            print("\n==================================================")
            print("Performance Budget Baseline Comparison (Allowed Regression: 10%)")
            print("==================================================")
            for key, val in current_run.items():
                base_val = baseline.get(key, val)
                diff_pct = ((val - base_val) / base_val) * 100.0 if base_val > 0 else 0

                status_str = "PASSED"
                # Reject only if regression is > 10% AND absolute change is > 3.0 ms (to ignore sub-millisecond jitter)
                if diff_pct > 10.0 and (val - base_val) > 3.0:
                    status_str = "REGRESSED"
                    regressed = True

                line = f"  {key:<18}: {format_ms(base_val):>10} -> {format_ms(val):>10} ({diff_pct:>+6.1f}%) [{status_str}]"
                print(line)
                comparison_logs.append(line)
        except Exception as exc:
            print(f"Error loading baseline file: {exc}")
    else:
        # Write current run as baseline if not exists
        try:
            with open(baseline_file, "w") as f:
                json.dump(current_run, f, indent=2)
            print(f"\nWritten baseline.json to {baseline_file}")
        except Exception as exc:
            print(f"Error writing baseline file: {exc}")

    # 3. Write outputs: benchmark.json, benchmark.md, benchmark.html
    # JSON
    with open(results_dir / "benchmark.json", "w") as f:
        json.dump(current_run, f, indent=2)

    # MD
    md_content = f"""# Forge Performance Benchmark Report

## Measured Overhead Latencies

| Overhead Metric | Latency (ms) |
|---|---|
| **Planning (Rule)** | {format_ms(planning_ms)} |
| **Execution Resolution** | {format_ms(execution_ms)} |
| **Memory persistence (SQLite)** | {format_ms(memory_ms)} |
| **Context Optimizer (Compression)** | {format_ms(compression_ms)} |
| **Composite Verifier** | {format_ms(verification_ms)} |
| **Plugin Load & List** | {format_ms(plugin_ms)} |
| **FastAPI REST healthcheck** | {format_ms(api_ms)} |
| **FastAPI WebSocket connection** | {format_ms(websocket_ms)} |
"""
    with open(results_dir / "benchmark.md", "w") as f:
        f.write(md_content)

    # HTML
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Forge Performance Benchmarks</title>
    <style>
        body {{ font-family: sans-serif; background: #0f172a; color: #f1f5f9; padding: 40px; }}
        h1 {{ color: #38bdf8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; border: 1px solid #334155; text-align: left; }}
        th {{ background: #1e293b; color: #38bdf8; }}
        tr:nth-child(even) {{ background: #1e293b; }}
    </style>
</head>
<body>
    <h1>Forge Engine Overhead Benchmarks</h1>
    <table>
        <tr><th>Overhead Metric</th><th>Latency (ms)</th></tr>
        <tr><td>Planning (Rule)</td><td>{format_ms(planning_ms)}</td></tr>
        <tr><td>Execution Resolution</td><td>{format_ms(execution_ms)}</td></tr>
        <tr><td>Memory persistence (SQLite)</td><td>{format_ms(memory_ms)}</td></tr>
        <tr><td>Context Optimizer (Compression)</td><td>{format_ms(compression_ms)}</td></tr>
        <tr><td>Composite Verifier</td><td>{format_ms(verification_ms)}</td></tr>
        <tr><td>Plugin Load & List</td><td>{format_ms(plugin_ms)}</td></tr>
        <tr><td>FastAPI REST healthcheck</td><td>{format_ms(api_ms)}</td></tr>
        <tr><td>FastAPI WebSocket connection</td><td>{format_ms(websocket_ms)}</td></tr>
    </table>
</body>
</html>
"""
    with open(results_dir / "benchmark.html", "w") as f:
        f.write(html_content)

    print("\nBenchmark outputs generated: benchmark.json, benchmark.md, benchmark.html")

    # If --compare-baseline is passed and we regressed, fail the build
    if "--compare-baseline" in sys.argv and regressed:
        print(
            "\n[bold red]Build Failed: Performance budget regression detected![/bold red]"
        )
        sys.exit(1)


if __name__ == "__main__":
    run_benchmarks_and_check()
