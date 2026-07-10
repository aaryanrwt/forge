# Forge Command Line Interface (CLI)

Forge ships with a powerful command line tool built using Typer and Rich to control goals, manage plugins, inspect performance, and run diagnostics.

## Subcommands Overview

### `forge init`
Initializes a new local workspace.
- **Description**: Creates the local SQLite database, configures the default settings file, and scaffolds the plugin directories.
- **Usage**:
  ```bash
  forge init
  ```

### `forge run`
Executes a new goal in the terminal.
- **Description**: Decomposes a goal into a DAG of tasks using the planner, and runs the execution loop with a real-time progress panel.
- **Usage**:
  ```bash
  forge run "Create a FastAPI python service and dockerize it"
  ```

### `forge resume`
Resumes a halted or failed execution.
- **Description**: Checks the task execution history in the database, skips already completed tasks, and resumes the remaining tasks.
- **Usage**:
  ```bash
  forge resume <execution_uuid>
  ```

### `forge status`
Display the active execution task graph status.
- **Description**: Prints a formatted DAG or list showing each task type, order index, status (PENDING, IN_PROGRESS, COMPLETED, FAILED), and retries count.
- **Usage**:
  ```bash
  forge status <execution_uuid>
  ```

### `forge logs`
Stream or display logs of an execution.
- **Usage**:
  ```bash
  forge logs <execution_uuid>
  ```

### `forge doctor`
Run environment health diagnostics.
- **Description**: Probes database write speeds, LLM provider availability, git/docker binaries on PATH, and plugin sandboxing schemas.
- **Parameters**:
  - `--fix`: Attempts to auto-repair missing folders or schemas.
  - `--system`: Prints system details (CPU, RAM, OS version).
- **Usage**:
  ```bash
  forge doctor --system --fix
  ```

### `forge trace`
Display execution span latency timeline.
- **Description**: Visualizes ASCII bars showing the breakdown of time spent in Planner, Executor, Verifier, Retry, Optimizer, and Memory.
- **Usage**:
  ```bash
  forge trace <execution_uuid>
  ```

### `forge inspect`
Prints the raw execution data and metrics in JSON format.
- **Usage**:
  ```bash
  forge inspect <execution_uuid>
  ```

### `forge graph`
Prints an ASCII tree of the task DAG and dependencies.
- **Usage**:
  ```bash
  forge graph <execution_uuid>
  ```

### `forge config`
Prints active configurations (Database URL, LLM model, timeouts, etc.).
- **Usage**:
  ```bash
  forge config
  ```

### `forge plugin`
Subgroup to scaffold and manage plugins.
- **Commands**:
  - `list`: Show installed plugins.
  - `install <path>`: Register a new local plugin folder.
  - `create <name>`: Scaffold a plugin template directory.
- **Usage**:
  ```bash
  forge plugin list
  forge plugin create custom-executor
  ```
