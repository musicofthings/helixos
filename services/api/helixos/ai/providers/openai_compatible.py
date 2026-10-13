"""OpenAI-compatible streaming provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from helixos.ai.providers.base import AgentPromptContext, Usage


class OpenAICompatibleProvider:
    """Stream chat completions from an OpenAI-compatible API."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        stream_usage: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._stream_usage = stream_usage
        self._transport = transport
        self.usage: Usage | None = None

    async def stream_response(
        self, context: AgentPromptContext, *, max_output_tokens: int
    ) -> AsyncIterator[str]:
        user_content = context.user_message
        if context.tool_summaries:
            user_content = f"{user_content}\n\nTool context:\n- " + "\n- ".join(
                context.tool_summaries
            )

        payload: dict[str, object] = {
            "model": self.model,
            "stream": True,
            # Hard ceiling on what one run can generate (and be billed for).
            "max_tokens": max_output_tokens,
            "messages": [
                {"role": "system", "content": context.system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if self._stream_usage:
            # Asks for a final chunk carrying the billed token counts.
            payload["stream_options"] = {"include_usage": True}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
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
                    reported = chunk.get("usage")
                    if reported:
                        self.usage = Usage(
                            input_tokens=int(reported.get("prompt_tokens") or 0),
                            output_tokens=int(reported.get("completion_tokens") or 0),
                        )
                    # The usage chunk has an empty choices list.
                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {}).get("content")
                        if delta:
                            yield delta
