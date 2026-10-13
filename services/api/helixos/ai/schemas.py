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


class UsageLine(BaseModel):
    """Spend in one window against its cap. Amounts are US dollars as decimal strings."""

    spent_usd: str
    cap_usd: str | None
    remaining_usd: str | None
    resets_at: str


class AiUsageSummary(BaseModel):
    """Current AI spend for an organization (admin view)."""

    organization_id: str
    currency: str
    organization_day: UsageLine
    organization_month: UsageLine
    you_day: UsageLine
    max_output_tokens_per_run: int
