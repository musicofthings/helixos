"""Provider protocol for agent runs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class AgentPromptContext:
    """Prompt context assembled for a run."""

    system_prompt: str
    user_message: str
    experiment_count: int
    experiment_title: str | None
    experiment_id: str | None
    sequence_length: int | None
    tool_summaries: list[str] = field(default_factory=list)


class AgentProvider(Protocol):
    """Streaming agent provider."""

    name: str

    async def stream_response(self, context: AgentPromptContext) -> AsyncIterator[str]:
        """Yield text fragments for SSE token events."""
