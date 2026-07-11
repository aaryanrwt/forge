"""Integration tests for the FastAPI REST and WebSocket API endpoints."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from forge.core.config import ForgeSettings
from forge.core.container import Container
from forge.presentation.api.main import app


@pytest.fixture
def api_client() -> TestClient:
    # Setup test container on app state
    settings = ForgeSettings(
        db_url="sqlite+aiosqlite:///:memory:",
        llm_provider="ollama",
        llm_model="llama3.2",
        planner_type="rule",
        log_level="DEBUG",
    )
    container = Container(settings=settings)
    asyncio.run(container.initialize())
    app.state.container = container

    client = TestClient(app)
    yield client

    asyncio.run(container.close())


def test_api_health_endpoints(api_client: TestClient) -> None:
    # Health check
    res = api_client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "version": "1.0.0"}

    # Readiness check
    res_ready = api_client.get("/health/ready")
    assert res_ready.status_code == 200
    assert res_ready.json() == {"status": "ready"}


def test_api_executions_crud_and_websocket(api_client: TestClient) -> None:
    # 1. Create execution (POST /api/v1/executions)
    res_create = api_client.post(
        "/api/v1/executions",
        json={"goal": "echo tests_passed"},
    )
    assert res_create.status_code == 201
    data = res_create.json()
    assert data["goal"] == "echo tests_passed"
    assert "id" in data

    exec_id = data["id"]

    # 2. Get execution (GET /api/v1/executions/{id})
    res_get = api_client.get(f"/api/v1/executions/{exec_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == exec_id

    # 3. List executions (GET /api/v1/executions)
    res_list = api_client.get("/api/v1/executions")
    assert res_list.status_code == 200
    assert len(res_list.json()["executions"]) >= 1

    # 4. Try Cancel Execution (POST /api/v1/executions/{id}/cancel)
    res_cancel = api_client.post(f"/api/v1/executions/{exec_id}/cancel")
    assert res_cancel.status_code == 202
    assert "submitted" in res_cancel.json()["message"]

    # 5. Try Resume Execution (POST /api/v1/executions/{id}/resume)
    res_resume = api_client.post(f"/api/v1/executions/{exec_id}/resume")
    assert res_resume.status_code == 202

    # 6. WebSocket subscription check (GET /ws/executions/{id})
    with api_client.websocket_connect(f"/ws/executions/{exec_id}"):
        # Send a keepalive ping message and receive event
        # (Since no events are fired instantly unless we trigger an orchestrator event,
        # we assert that the socket connected successfully and can be closed without errors)
        pass
