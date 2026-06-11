"""Deterministic stub provider for local development and CI."""

from __future__ import annotations

from collections.abc import AsyncIterator

from helixos.ai.providers.base import AgentPromptContext


class StubAgentProvider:
    """Rule-based provider that never calls external models."""

    name = "stub"

    async def stream_response(self, context: AgentPromptContext) -> AsyncIterator[str]:
        focus = context.experiment_title or context.experiment_id or "the active workspace"
        sequence_hint = (
            f"{context.sequence_length} bp" if context.sequence_length else "no sequence context supplied"
        )
        tool_hint = ", ".join(context.tool_summaries) if context.tool_summaries else "no tool summaries"
        response = (
            f"{context.system_prompt} "
            f"Based on your request ({context.user_message.strip()}), review {focus}. "
            f"The workspace currently has {context.experiment_count} experiment record(s). "
            f"Sequence context: {sequence_hint}. Tool context: {tool_hint}. "
            "Suggested next actions: verify reagent lots, confirm observations are recorded, "
            "and move the record to review only after wet-lab steps are documented. "
            "This is a suggestion, not an experimental observation."
        )
        for token in response.split():
            yield f"{token} "
