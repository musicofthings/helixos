"""Runtime settings for AI providers."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AISettings:
    """Environment-driven AI configuration."""

    provider: str
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str
    vertex_project: str | None
    vertex_location: str
    vertex_model: str

    @classmethod
    def from_env(cls) -> "AISettings":
        return cls(
            provider=os.getenv("HELIX_AI_PROVIDER", "stub").strip().lower(),
            openai_api_key=os.getenv("HELIX_OPENAI_API_KEY"),
            openai_base_url=os.getenv("HELIX_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_model=os.getenv("HELIX_OPENAI_MODEL", "gpt-4o-mini"),
            vertex_project=os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("HELIX_VERTEX_PROJECT"),
            vertex_location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1"),
            vertex_model=os.getenv("HELIX_VERTEX_MODEL", "gemini-2.0-flash-001"),
        )

    @property
    def effective_provider(self) -> str:
        if self.provider == "openai" and not self.openai_api_key:
            return "stub"
        if self.provider == "vertex" and not self.vertex_project:
            return "stub"
        return self.provider
