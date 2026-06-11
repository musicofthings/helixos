"""Pydantic schemas for audit events."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Public audit event representation."""

    id: str
    organization_id: str
    actor_subject: str
    event_type: str
    resource_type: str | None = None
    resource_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    previous_hash: str | None = None
    event_hash: str | None = None
    sequence_number: int | None = None


class AuditChainVerification(BaseModel):
    """Result of verifying an organization audit chain."""

    organization_id: str
    valid: bool
    event_count: int
    head_hash: str | None = None
    message: str
