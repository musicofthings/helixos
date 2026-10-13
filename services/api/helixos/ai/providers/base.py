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


@dataclass(frozen=True)
class Usage:
    """Tokens the model provider billed for one run."""

    input_tokens: int
    output_tokens: int


class AgentProvider(Protocol):
    """Streaming agent provider.

    A provider instance serves a single run. After ``stream_response`` finishes
    (or is abandoned) ``usage`` holds what the provider reported, or ``None``
    when it reports nothing and the caller must estimate.
    """

    name: str
    model: str | None
    usage: Usage | None

    async def stream_response(
        self, context: AgentPromptContext, *, max_output_tokens: int
    ) -> AsyncIterator[str]:
        """Yield text fragments for SSE token events, generating at most ``max_output_tokens``."""
