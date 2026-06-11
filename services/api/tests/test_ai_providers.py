"""Tests for AI provider selection."""

from helixos.ai.providers import get_agent_provider
from helixos.ai.providers.stub import StubAgentProvider
from helixos.ai.settings import AISettings


def test_provider_falls_back_to_stub_without_api_key(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_AI_PROVIDER", "openai")
    monkeypatch.delenv("HELIX_OPENAI_API_KEY", raising=False)

    settings = AISettings.from_env()
    assert settings.effective_provider == "stub"
    provider = get_agent_provider()
    assert isinstance(provider, StubAgentProvider)


def test_provider_falls_back_to_stub_without_vertex_project(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_AI_PROVIDER", "vertex")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("HELIX_VERTEX_PROJECT", raising=False)

    settings = AISettings.from_env()
    assert settings.effective_provider == "stub"
    provider = get_agent_provider()
    assert isinstance(provider, StubAgentProvider)
