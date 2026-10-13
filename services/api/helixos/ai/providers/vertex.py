"""Vertex AI streaming provider."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from helixos.ai.providers.base import AgentPromptContext, Usage


class VertexAIProvider:
    """Stream responses from Vertex AI Gemini models."""

    name = "vertex"

    def __init__(
        self, *, project: str, location: str, model: str, client: Any | None = None
    ) -> None:
        if client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "google-genai is required for the Vertex provider. "
                    "Install with: pip install -e 'services/api[vertex]'"
                ) from exc
            client = genai.Client(vertexai=True, project=project, location=location)

        self._client = client
        self.model = model
        self.usage: Usage | None = None

    async def stream_response(
        self, context: AgentPromptContext, *, max_output_tokens: int
    ) -> AsyncIterator[str]:
        user_content = context.user_message
        if context.tool_summaries:
            user_content = f"{user_content}\n\nTool context:\n- " + "\n- ".join(
                context.tool_summaries
            )

        stream = self._client.models.generate_content_stream(
            model=self.model,
            contents=[
                {
                    "role": "user",
                    "parts": [{"text": f"{context.system_prompt}\n\n{user_content}"}],
                },
            ],
            # Hard ceiling on what one run can generate (and be billed for).
            config={"max_output_tokens": max_output_tokens},
        )

        # The SDK stream is synchronous: pull each chunk on a worker thread so a
        # run never blocks the event loop (and every other request with it).
        iterator = iter(stream)
        done = object()
        while True:
            chunk = await asyncio.to_thread(next, iterator, done)
            if chunk is done:
                break
            meta = getattr(chunk, "usage_metadata", None)
            if meta is not None:
                self.usage = Usage(
                    input_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
                    output_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
                )
            text = getattr(chunk, "text", None)
            if text:
                yield text
