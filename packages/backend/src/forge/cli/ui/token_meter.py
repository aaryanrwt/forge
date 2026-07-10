"""UI component to render LLM token usage stats."""
from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from forge.core.domain.models import TokenUsage


def render_token_meter(usage: TokenUsage) -> Panel:
    """Return a Panel displaying prompt, completion, total tokens and cost estimations."""
    text = Text()
    text.append("Token Consumption Meter\n\n", style="bold cyan")
    text.append(f"  Prompt Tokens:     {usage.prompt_tokens}\n", style="white")
    text.append(f"  Completion Tokens: {usage.completion_tokens}\n", style="white")
    text.append(f"  Total Tokens:      {usage.total_tokens}\n", style="bold white")
    
    # Calculate estimated cost if not populated (e.g. Ollama is $0.0, OpenAI has estimates)
    cost = usage.cost_usd
    if cost == 0.0 and usage.total_tokens > 0:
        # Heuristic: $0.15 per 1M tokens (gpt-4o-mini scale)
        cost = (usage.total_tokens / 1_000_000.0) * 0.15

    text.append(f"  Estimated Cost:    ${cost:.6f} USD\n", style="green")

    return Panel(
        text,
        title="[bold yellow]Resource Usage[/bold yellow]",
        border_style="yellow",
        width=40,
    )
