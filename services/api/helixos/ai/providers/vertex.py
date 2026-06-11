"""Vertex AI streaming provider."""

from __future__ import annotations

from collections.abc import AsyncIterator

from helixos.ai.providers.base import AgentPromptContext


class VertexAIProvider:
    """Stream responses from Vertex AI Gemini models."""

    name = "vertex"

    def __init__(self, *, project: str, location: str, model: str) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "google-genai is required for the Vertex provider. "
                "Install with: pip install -e 'services/api[vertex]'"
            ) from exc

        self._client = genai.Client(vertexai=True, project=project, location=location)
        self._model = model

    async def stream_response(self, context: AgentPromptContext) -> AsyncIterator[str]:
        user_content = context.user_message
        if context.tool_summaries:
            user_content = f"{user_content}\n\nTool context:\n- " + "\n- ".join(context.tool_summaries)

        stream = self._client.models.generate_content_stream(
            model=self._model,
            contents=[
                {"role": "user", "parts": [{"text": f"{context.system_prompt}\n\n{user_content}"}]},
            ],
        )

        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text
