"""OpenAI-compatible streaming provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from helixos.ai.providers.base import AgentPromptContext


class OpenAICompatibleProvider:
    """Stream chat completions from an OpenAI-compatible API."""

    name = "openai"

    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def stream_response(self, context: AgentPromptContext) -> AsyncIterator[str]:
        user_content = context.user_message
        if context.tool_summaries:
            user_content = f"{user_content}\n\nTool context:\n- " + "\n- ".join(context.tool_summaries)

        payload = {
            "model": self._model,
            "stream": True,
            "messages": [
                {"role": "system", "content": context.system_prompt},
                {"role": "user", "content": user_content},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
