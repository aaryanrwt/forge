# Forge REST and WebSocket API Reference

Forge exposes a FastAPI server under `/api/v1/` for external client integrations.

## REST Endpoints

### Health check
- **GET** `/health`
  - **Description**: Basic service check.
  - **Response**:
    ```json
    { "status": "ok", "version": "1.0.0" }
    ```
- **GET** `/health/ready`
  - **Description**: Confirms the database connections and system setups are ready to plan/execute.

### Executions
- **POST** `/api/v1/executions`
  - **Description**: Plans a new execution goal.
  - **Payload**:
    ```json
    { "goal": "inbound task goal description" }
    ```
- **GET** `/api/v1/executions`
  - **Description**: List recent executions.
- **GET** `/api/v1/executions/{id}`
  - **Description**: Retrieve a detailed execution object containing its task list.
- **POST** `/api/v1/executions/{id}/cancel`
  - **Description**: Halts a running execution loop.
- **POST** `/api/v1/executions/{id}/resume`
  - **Description**: Re-queues a failed execution task graph.

### Traces & Statistics
- **GET** `/api/v1/executions/{id}/telemetry`
  - **Description**: Returns execution latencies, spans, and metrics.

---

## WebSocket Interface

Stream events in real time by establishing a WebSocket connection to:
```
ws://localhost:8000/ws/executions/{id}
```

### Event Payload Formats

Every broadcast event follows this schema:
```json
{
  "event_type": "ExecutionStarted | TaskStarted | VerificationCompleted | TaskCompleted | TaskFailed | TaskRetried | ExecutionCompleted",
  "timestamp": "ISO-8601",
  "data": { ... }
}
```
*   **TaskStarted**: Triggered when an executor starts executing a task. Contains `task_id` and `started_at`.
*   **VerificationCompleted**: Emitted after the verifier evaluates a task. Contains `success` (boolean) and `details` dictionary.
*   **TaskCompleted**: Emitted when a task completes successfully.
*   **ExecutionCompleted**: Emitted when all tasks finish or a permanent failure terminates the loop.
