# Forge Execution Flow

This document details the step-by-step state machine flow of the Forge AI Execution Layer.

## Core State Machine Loop

```
            User Goal
                 │
                 ▼
             Planner (Rule / LLM)
                 │
                 ▼
             Executor (Shell / Py / Docker / Git / MCP / Model)
                 │
                 ▼
             Verifier (Exit Code / File / Pattern)
                 │
      ┌──────────┴──────────┐
      │ Success             │
      ▼                     ▼
   Complete        Retry Controller (Circuit Breaker)
                            │
                            ▼
                     Context Optimizer (Token sliding window)
                            │
                            ▼
                      Memory Service (SQLite persist)
                            │
                            └──────────► Planner (Next Step)
```

## Detailed Execution Steps

### 1. Planning Stage
- The `Orchestrator` receives a natural language goal.
- It calls `Planner.plan(goal)`.
- If the LLM is unreachable, the planner falls back to the deterministic offline `RulePlanner` using regex keywords.
- Generates a List of `Task` objects representing a Directed Acyclic Graph (DAG).

### 2. Execution Stage
- The orchestrator selects the next pending task.
- Queries `ExecutorService` which selects the matching executor (e.g. `ShellExecutor`, `PythonExecutor`, `GitExecutor`).
- Executes the task logic within configured timeouts.
- Safe operations are enforced: Git operations block `push`, and Docker operations allow read-heavy commands (`ps`, `build`, `run`) only.

### 3. Verification Stage
- The completed task is sent to `CompositeVerifier`.
- Verifiers assert:
  - Exit code matches expectation.
  - Required files exist on disk.
  - Subprocess stdout matches regex patterns.
- Returns a boolean success verdict.

### 4. Retry & Circuit Breakers
- If verification fails, the orchestrator consults `RetryController`.
- Applies exponential backoff delays.
- Checks circuit breaker thresholds: if a task type crashes repeatedly, it trips the breaker to prevent resource waste.
- Detects infinite repetition loops by calculating task output MD5 hashes.

### 5. Context Optimization & Memory
- Logs and context messages are stored in SQLite via `sqlite_repository.py`.
- `RollingContextOptimizer` truncates verbose outputs and applies sliding window limits to avoid context window size overflows.
- State is synchronized, and the loop resumes for subsequent steps.
