"""Pydantic schemas for authentication and organizations."""

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from helixos.auth.roles import OrgRole

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    """Lowercase and validate an email address."""
    cleaned = value.strip().lower()
    if len(cleaned) > 254 or not _EMAIL.match(cleaned):
        raise ValueError("must be a valid email address")
    return cleaned


class Organization(BaseModel):
    """Tenant boundary visible to an authenticated caller."""

    id: str
    name: str
    slug: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # The caller's role here; filled in when listing for an authenticated actor.
    role: OrgRole | None = None


class Actor(BaseModel):
    """Authenticated caller context extracted from a bearer token.

    ``subject`` is the stable internal user id and is what audit events and
    workspace shares record. ``email`` is set only when the identity provider
    asserts it is verified, so it can safely match email-addressed shares.
    ``roles`` maps organization id to :class:`OrgRole`; an actor without roles
    (demo/dev tokens) is treated as a full member of its organizations.
    """

    subject: str
    organization_ids: list[str]
    permissions: list[str] = Field(default_factory=list)
    email: str | None = None
    roles: dict[str, str] = Field(default_factory=dict)

    @property
    def identities(self) -> list[str]:
        """Every string a workspace share may address this actor by."""
        return [self.subject, self.email] if self.email else [self.subject]


class OrgMember(BaseModel):
    user_id: str
    email: str | None
    display_name: str | None = None
    role: OrgRole
    joined_at: datetime


class OrgMemberInvite(BaseModel):
    id: str
    email: str
    role: OrgRole
    invited_by: str
    created_at: datetime


class OrgMembers(BaseModel):
    members: list[OrgMember]
    invites: list[OrgMemberInvite]


class MemberAddRequest(BaseModel):
    """Add an existing user, or invite an email address that has not signed in yet."""

    email: str
    role: OrgRole

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class MemberRoleUpdate(BaseModel):
    role: OrgRole


class MemberAddResult(BaseModel):
    member: OrgMember | None = None
    invite: OrgMemberInvite | None = None
