"""Agent provider registry."""

from helixos.ai.providers.base import AgentPromptContext, AgentProvider
from helixos.ai.providers.openai_compatible import OpenAICompatibleProvider
from helixos.ai.providers.stub import StubAgentProvider
from helixos.ai.providers.vertex import VertexAIProvider
from helixos.ai.settings import AISettings


def get_agent_provider() -> AgentProvider:
    """Return the configured provider."""
    settings = AISettings.from_env()
    if settings.effective_provider == "openai" and settings.openai_api_key:
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    if settings.effective_provider == "vertex" and settings.vertex_project:
        return VertexAIProvider(
            project=settings.vertex_project,
            location=settings.vertex_location,
            model=settings.vertex_model,
        )
    return StubAgentProvider()


__all__ = [
    "AgentPromptContext",
    "AgentProvider",
    "OpenAICompatibleProvider",
    "StubAgentProvider",
    "VertexAIProvider",
    "get_agent_provider",
]
