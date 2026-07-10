"""Forge context optimizer — reduces LLM context window token size.

Implements `RollingContextOptimizer` which truncates long tool output and applies
a sliding window to recent dialogue turns.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from forge.core.domain.interfaces import IContextOptimizer

logger = logging.getLogger(__name__)


class RollingContextOptimizer(IContextOptimizer):
    """Context optimizer that applies length truncation and sliding window constraints.

    Maintains a record of token savings and ensures that system prompts
    and final messages are preserved, while middle turns are pruned or summarized.
    """

    class ContextWindow:
        """Helper to track token sizes and window entries."""

        def __init__(self, max_tokens: int = 8000) -> None:
            self.max_tokens = max_tokens
            self.total_estimated_tokens = 0

        def estimate_tokens(self, text: str) -> int:
            """Simple heuristic: 4 characters ≈ 1 token."""
            return len(text) // 4

    def __init__(self, max_window_size: int = 10) -> None:
        """Initialize the optimizer.

        Args:
            max_window_size: Maximum number of recent messages to keep.
        """
        self.max_window_size = max_window_size
        self._token_savings = 0
        self._window = self.ContextWindow()

    async def optimize(
        self, context: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Prune, truncate, and filter a list of chat messages to fit context limits.

        Rules:
        - Keep the system prompt (typically index 0, if present)
        - Truncate individual message contents if they exceed 2000 chars
        - Keep at most the last `max_window_size` messages (plus the system prompt)
        """
        if not context:
            return []

        optimized: List[Dict[str, Any]] = []
        system_msg: Optional[Dict[str, Any]] = None

        # Check if first message is a system message
        if context[0].get("role") == "system":
            system_msg = context[0]
            remaining_messages = context[1:]
        else:
            remaining_messages = context

        # 1. Truncate long contents (especially tool output or verbose responses)
        truncated_messages: List[Dict[str, Any]] = []
        for msg in remaining_messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            
            # If content is a dict/json, convert to string
            if not isinstance(content, str):
                content = str(content)

            original_len = len(content)
            
            # Truncate if > 2000 characters
            if len(content) > 2000:
                content = content[:1000] + "\n...[truncated due to length]...\n" + content[-1000:]
                # Calculate estimated saved tokens
                saved_chars = original_len - len(content)
                self._token_savings += self._window.estimate_tokens("a" * saved_chars)
                logger.debug("Truncated message from role %s, saved ~%d chars", role, saved_chars)

            truncated_messages.append({**msg, "content": content})

        # 2. Sliding window: keep only the last max_window_size messages
        if len(truncated_messages) > self.max_window_size:
            discarded_count = len(truncated_messages) - self.max_window_size
            # Accumulate savings from discarded messages
            for msg in truncated_messages[:discarded_count]:
                content = msg.get("content", "")
                self._token_savings += self._window.estimate_tokens(content)

            truncated_messages = truncated_messages[-self.max_window_size:]
            logger.info("Context sliding window dropped %d messages", discarded_count)

        # 3. Re-assemble with system message at the beginning
        if system_msg:
            optimized.append(system_msg)
        
        optimized.extend(truncated_messages)
        return optimized

    def get_token_savings(self) -> int:
        """Return cumulative token savings."""
        return self._token_savings
