"""Base class for all LLM provider adapters.

Provides shared utilities (JSON extraction from markdown-fenced responses)
on top of the ILLMProvider abstract interface.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from forge.core.domain.interfaces import ILLMProvider
from forge.core.domain.models import TokenUsage


class BaseLLMProvider(ILLMProvider):
    """Shared utilities for LLM provider adapters.

    Concrete providers should implement ``complete()``, ``is_available()``,
    ``provider_name``, and ``model_name``.  Everything else is optional.
    """

    async def complete_json(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
    ) -> tuple[Any, TokenUsage]:
        """Call ``complete()`` and parse the response as JSON.

        Handles markdown code fences (e.g. ```json ... ```) by stripping
        them before parsing.  Raises ``json.JSONDecodeError`` if the response
        cannot be parsed.

        Args:
            messages: OpenAI-style message dicts with 'role' and 'content'.
            max_tokens: Maximum tokens to generate.

        Returns:
            A tuple of (parsed_object, TokenUsage).
        """
        raw, usage = await self.complete(messages, max_tokens=max_tokens)
        cleaned = raw.strip()

        # Strip markdown code fences if present (```json or ```)
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # Drop the opening fence line (```json or ```)
            lines = lines[1:]
            # Drop the closing fence line if present
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        return json.loads(cleaned), usage
