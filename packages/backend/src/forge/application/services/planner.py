"""Forge planner services — RulePlanner, LLMPlanner, and FallbackPlanner.

Planners decompose a natural-language goal into an ordered list of Tasks
wrapped in a new Execution.

- ``RulePlanner``: deterministic keyword-based planning, works offline.
- ``LLMPlanner``: sends the goal to an LLM and parses the JSON task list.
- ``FallbackPlanner``: tries LLMPlanner first, falls back to RulePlanner.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from forge.core.domain.exceptions import PlannerError
from forge.core.domain.interfaces import ILLMProvider, IPlanner
from forge.core.domain.models import Execution, Task, TaskStatus, TaskType

logger = logging.getLogger(__name__)

# ── Keyword patterns for RulePlanner ─────────────────────────────────────────

_RULE_MAP: List[tuple[re.Pattern[str], TaskType, str]] = [
    (re.compile(r"\b(run|execute|shell|bash|cmd)\b", re.I), TaskType.SHELL, "shell"),
    (re.compile(r"\b(python|py|script)\b", re.I), TaskType.PYTHON, "python"),
    (re.compile(r"\b(git|clone|commit|diff|status)\b", re.I), TaskType.GIT, "git"),
    (re.compile(r"\b(docker|container|image|build)\b", re.I), TaskType.DOCKER, "docker"),
    (re.compile(r"\b(mcp|tool|call tool)\b", re.I), TaskType.MCP, "mcp"),
]

_PLAN_SYSTEM_PROMPT = """\
You are a planning assistant for the Forge AI Execution Layer.
Given a user goal, decompose it into a list of concrete, executable tasks.
Return ONLY a valid JSON array of task objects (no markdown, no prose).

Each task object must have these keys:
  "name"        : short task name (string)
  "description" : detailed description (string)
  "task_type"   : one of "cli", "python", "mcp", "git", "docker", "shell", "model"
  "inputs"      : dict of executor-specific inputs (may be empty {})
  "order_index" : integer starting at 0

Example for "echo hello":
[
  {
    "name": "Echo hello",
    "description": "Run echo hello in the shell",
    "task_type": "shell",
    "inputs": {"command": "echo hello"},
    "order_index": 0
  }
]
"""


class RulePlanner(IPlanner):
    """Deterministic keyword-based planner — works fully offline.

    Matches goal keywords to task types and produces a single task.
    Suitable as a fallback when no LLM is available.
    """

    async def plan(self, goal: str) -> Execution:
        """Create an Execution with a single task inferred from keyword rules."""
        execution = Execution(goal=goal, status=TaskStatus.PENDING)
        task_type = self._infer_type(goal)
        inputs = self._build_inputs(goal, task_type)

        task = Task(
            execution_id=execution.id,
            name=goal[:80],
            description=goal,
            task_type=task_type,
            inputs=inputs,
            order_index=0,
        )
        execution.tasks.append(task)
        logger.debug(
            "RulePlanner produced 1 task: type=%s for goal=%r",
            task_type.value,
            goal[:60],
        )
        return execution

    def _infer_type(self, goal: str) -> TaskType:
        """Return the best-matching TaskType for the goal text."""
        for pattern, task_type, _ in _RULE_MAP:
            if pattern.search(goal):
                return task_type
        return TaskType.SHELL  # default fallback

    def _build_inputs(self, goal: str, task_type: TaskType) -> Dict[str, Any]:
        """Build a minimal inputs dict appropriate for *task_type*."""
        if task_type in (TaskType.SHELL, TaskType.CLI):
            return {"command": goal}
        if task_type == TaskType.PYTHON:
            return {"code": f"# Auto-generated\nresult = None\n# Goal: {goal}"}
        if task_type == TaskType.GIT:
            return {"operation": "status", "args": []}
        if task_type == TaskType.DOCKER:
            return {"operation": "ps", "args": []}
        return {}


class LLMPlanner(IPlanner):
    """LLM-powered planner that decomposes goals via structured JSON output.

    Sends the goal to an ILLMProvider and parses the returned JSON task list.
    Falls back to a single SHELL task if parsing fails.
    """

    def __init__(self, llm: ILLMProvider, max_tokens: int = 2048) -> None:
        self._llm = llm
        self._max_tokens = max_tokens

    async def plan(self, goal: str) -> Execution:
        """Call the LLM to produce a task plan for *goal*.

        Raises:
            PlannerError: If the LLM response cannot be parsed as a task list.
        """
        execution = Execution(goal=goal, status=TaskStatus.PENDING)
        messages = [
            {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": f"Goal: {goal}"},
        ]
        try:
            raw, usage = await self._llm.complete(messages, max_tokens=self._max_tokens)
            execution.token_usage = usage
            task_dicts = self._parse_response(raw)
        except PlannerError:
            raise
        except Exception as exc:
            raise PlannerError(f"LLMPlanner failed: {exc}") from exc

        for idx, td in enumerate(task_dicts):
            task = self._dict_to_task(execution.id, td, idx)
            execution.tasks.append(task)

        if not execution.tasks:
            raise PlannerError("LLM returned an empty task list")

        logger.info(
            "LLMPlanner produced %d tasks for goal=%r", len(execution.tasks), goal[:60]
        )
        return execution

    def _parse_response(self, raw: str) -> List[Dict[str, Any]]:
        """Extract a JSON array from the LLM response, stripping code fences."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        # Find first '[' to handle responses with leading prose
        bracket_idx = cleaned.find("[")
        if bracket_idx != -1:
            cleaned = cleaned[bracket_idx:]

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise PlannerError(
                f"Could not parse LLM response as JSON: {exc}\nRaw: {raw[:300]}"
            ) from exc

        if not isinstance(parsed, list):
            raise PlannerError(
                f"Expected a JSON array from LLM planner, got {type(parsed).__name__}"
            )
        return parsed

    def _dict_to_task(
        self, execution_id: Any, td: Dict[str, Any], fallback_index: int
    ) -> Task:
        """Convert a raw task dict from the LLM into a Task domain object."""
        raw_type = td.get("task_type", "shell").lower()
        try:
            task_type = TaskType(raw_type)
        except ValueError:
            logger.warning("Unknown task_type '%s'; defaulting to SHELL", raw_type)
            task_type = TaskType.SHELL

        return Task(
            execution_id=execution_id,
            name=str(td.get("name", "Unnamed task")),
            description=str(td.get("description", "")),
            task_type=task_type,
            inputs=td.get("inputs", {}),
            order_index=int(td.get("order_index", fallback_index)),
        )


class FallbackPlanner(IPlanner):
    """Tries LLMPlanner first; falls back to RulePlanner on any error.

    This is the recommended default for production: rich planning when an LLM
    is available, degraded-but-functional planning when it is not.
    """

    def __init__(self, llm: ILLMProvider) -> None:
        self._llm_planner = LLMPlanner(llm)
        self._rule_planner = RulePlanner()

    async def plan(self, goal: str) -> Execution:
        """Attempt LLM planning; fall back to rule planning on failure."""
        try:
            return await self._llm_planner.plan(goal)
        except Exception as exc:
            logger.warning(
                "LLMPlanner failed (%s); falling back to RulePlanner", exc
            )
            return await self._rule_planner.plan(goal)


# Backwards-compatible alias used by the existing container
SimplePlanner = RulePlanner
