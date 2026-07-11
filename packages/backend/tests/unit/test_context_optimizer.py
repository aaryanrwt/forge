"""Unit tests for RollingContextOptimizer."""

from __future__ import annotations

import pytest

from forge.application.services.context_optimizer import RollingContextOptimizer


@pytest.mark.asyncio
async def test_sliding_window_filtering() -> None:
    optimizer = RollingContextOptimizer(max_window_size=3)

    # 5 dialogue turns + 1 system message
    context = [
        {"role": "system", "content": "You are Forge."},
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "resp 1"},
        {"role": "user", "content": "turn 2"},
        {"role": "assistant", "content": "resp 2"},
        {"role": "user", "content": "turn 3"},
    ]

    optimized = await optimizer.optimize(context)

    # Output should include:
    # 1. System prompt (preserved)
    # 2. Last 3 turns (turn 2, resp 2, turn 3)
    assert len(optimized) == 4
    assert optimized[0]["role"] == "system"
    assert optimized[1]["content"] == "turn 2"
    assert optimized[2]["content"] == "resp 2"
    assert optimized[3]["content"] == "turn 3"

    # Savings should be tracked
    assert optimizer.get_token_savings() > 0


@pytest.mark.asyncio
async def test_message_truncation() -> None:
    optimizer = RollingContextOptimizer(max_window_size=10)

    # Message content > 2000 chars
    long_content = "A" * 3000
    context = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": long_content},
    ]

    optimized = await optimizer.optimize(context)
    assert len(optimized) == 2

    optimized_content = optimized[1]["content"]
    assert len(optimized_content) < 3000
    assert "...[truncated due to length]..." in optimized_content
    assert optimizer.get_token_savings() > 0


stream_logs = """
Some logs
"""
