"""Authentication and organization services."""

import base64
import json
from typing import Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from helixos.auth.schemas import Actor, Organization
from helixos.errors import api_error

bearer_scheme = HTTPBearer(auto_error=False)

ORGANIZATIONS: tuple[Organization, ...] = (
    Organization(id="org_demo", name="Demo Molecular Lab", slug="demo-molecular-lab"),
    Organization(id="org_qc", name="QC Genomics", slug="qc-genomics"),
)

DEMO_TOKENS: dict[str, Actor] = {
    "demo-admin-token": Actor(
        subject="user_demo_admin",
        organization_ids=["org_demo", "org_qc"],
        permissions=["organizations:read", "experiments:write", "sequences:read", "mcp:read"],
    ),
    "org-demo-token": Actor(
        subject="user_demo_scientist",
        organization_ids=["org_demo"],
        permissions=["organizations:read", "experiments:write", "sequences:read", "mcp:read"],
    ),
}


class OrganizationService:
    """Coordinates organization visibility checks."""

    def list_for_actor(self, actor: Actor) -> list[Organization]:
        """List organizations visible to an authenticated actor."""
        visible = set(actor.organization_ids)
        return [organization for organization in ORGANIZATIONS if organization.id in visible]

    def require_access(self, actor: Actor, organization_id: str) -> None:
        """Raise when an actor cannot access a tenant."""
        if organization_id not in actor.organization_ids:
            raise api_error(
                status_code=403,
                code="forbidden",
                message="Caller does not have access to this organization",
                details={"organization_id": organization_id},
            )


def _decode_unverified_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode a JWT-like payload without signature verification for local dev.

    Production integrations should replace this with the configured OIDC/JWKS
    verifier. This keeps the starter kit's bearer-token contract testable
    without adding provider-specific dependencies.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{payload_segment}{padding}")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def actor_from_token(token: str) -> Actor | None:
    """Resolve an actor from supported local-development bearer tokens."""
    if token in DEMO_TOKENS:
        return DEMO_TOKENS[token]

    payload = _decode_unverified_jwt_payload(token)
    if payload is None:
        return None

    organization_ids = payload.get("organization_ids") or payload.get("orgs")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not isinstance(organization_ids, list):
        return None

    permissions = payload.get("permissions", [])
    return Actor(
        subject=subject,
        organization_ids=[item for item in organization_ids if isinstance(item, str)],
        permissions=[item for item in permissions if isinstance(item, str)],
    )


def get_current_actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> Actor:
    """Extract the authenticated actor from a bearer token."""
    if credentials is None:
        raise api_error(status_code=401, code="unauthorized", message="Bearer token is required")

    actor = actor_from_token(credentials.credentials)
    if actor is None:
        raise api_error(status_code=401, code="unauthorized", message="Bearer token is invalid")
    return actor


organization_service = OrganizationService()
