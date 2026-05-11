"""Pydantic schemas for authentication and organizations."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Organization(BaseModel):
    """Tenant boundary visible to an authenticated caller."""

    id: str
    name: str
    slug: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Actor(BaseModel):
    """Authenticated caller context extracted from a bearer token."""

    subject: str
    organization_ids: list[str]
    permissions: list[str] = Field(default_factory=list)
