"""Unit tests for offline RulePlanner goal decomposition."""
from __future__ import annotations

import pytest

from forge.application.services.planner import RulePlanner
from forge.core.domain.models import TaskStatus, TaskType


@pytest.mark.asyncio
async def test_rule_planner_python_keyword() -> None:
    planner = RulePlanner()
    goal = "Create a python script that reads csv data"
    
    execution = await planner.plan(goal)
    assert execution.status == TaskStatus.PENDING
    assert len(execution.tasks) == 1
    
    task = execution.tasks[0]
    assert task.task_type == TaskType.PYTHON
    assert "code" in task.inputs
    assert task.inputs["code"].startswith("# Auto-generated")


@pytest.mark.asyncio
async def test_rule_planner_git_keyword() -> None:
    planner = RulePlanner()
    goal = "git status of the repository"
    
    execution = await planner.plan(goal)
    assert len(execution.tasks) == 1
    assert execution.tasks[0].task_type == TaskType.GIT
    assert execution.tasks[0].inputs == {"operation": "status", "args": []}


@pytest.mark.asyncio
async def test_rule_planner_default_shell() -> None:
    planner = RulePlanner()
    goal = "Echo hello world"
    
    execution = await planner.plan(goal)
    assert len(execution.tasks) == 1
    assert execution.tasks[0].task_type == TaskType.SHELL
    assert execution.tasks[0].inputs == {"command": "Echo hello world"}
