"""Pydantic schemas for AI sessions and agent runs."""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentSessionCreate(BaseModel):
    """Payload for creating an agent session."""

    organization_id: str


class AgentSession(BaseModel):
    """Persisted agent session."""

    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime


class AgentRunContext(BaseModel):
    """Optional lab context injected into an agent run."""

    experiment_id: str | None = None
    experiment_title: str | None = None
    sequence_length: int | None = None


class AgentRunCreate(BaseModel):
    """Payload for starting an agent run."""

    session_id: str
    message: str = Field(min_length=1)
    context: AgentRunContext = Field(default_factory=AgentRunContext)


class AgentStreamEvent(BaseModel):
    """Server-sent event emitted during an agent run."""

    event: str
    data: dict[str, object]
