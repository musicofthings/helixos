"""Authentication and organization services."""

import base64
import json
import logging
from typing import Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from helixos import config
from helixos.auth.oidc import OidcError, OidcVerifier
from helixos.auth.roles import (
    ROLE_PERMISSIONS,
    WORKSPACE_ACCESS,
    OrgRole,
    WorkspaceAccess,
    permissions_for,
)
from helixos.auth.schemas import Actor, Organization
from helixos.auth.store import auth_store
from helixos.db.settings import get_database_settings
from helixos.errors import api_error
from helixos.observability import bind

logger = logging.getLogger("helixos.auth")

bearer_scheme = HTTPBearer(auto_error=False)

ORGANIZATIONS: tuple[Organization, ...] = (
    Organization(id="org_demo", name="Demo Molecular Lab", slug="demo-molecular-lab"),
    Organization(id="org_qc", name="QC Genomics", slug="qc-genomics"),
)

_DEMO_PERMISSIONS = [
    "organizations:read",
    "experiments:write",
    "sequences:read",
    "mcp:read",
    "ai:run",
]

DEMO_TOKENS: dict[str, Actor] = {
    "demo-admin-token": Actor(
        subject="user_demo_admin",
        organization_ids=["org_demo", "org_qc"],
        permissions=_DEMO_PERMISSIONS,
        roles={"org_demo": OrgRole.ADMIN.value, "org_qc": OrgRole.ADMIN.value},
    ),
    "org-demo-token": Actor(
        subject="user_demo_scientist",
        organization_ids=["org_demo"],
        permissions=_DEMO_PERMISSIONS,
        roles={"org_demo": OrgRole.SCIENTIST.value},
    ),
}


def _forbidden(message: str, **details: Any):
    return api_error(
        status_code=403, code="forbidden", message=message, details=details
    )


class OrganizationService:
    """Coordinates organization visibility and role checks."""

    def list_for_actor(self, actor: Actor) -> list[Organization]:
        """List organizations visible to an authenticated actor."""
        visible = set(actor.organization_ids)
        organizations: list[Organization] = []
        if config.demo_tokens_enabled():
            organizations.extend(org for org in ORGANIZATIONS if org.id in visible)
        if get_database_settings().is_configured:
            known = {org.id for org in organizations}
            wanted = sorted(visible - known)
            if wanted:
                organizations.extend(auth_store.list_organizations(wanted))
        return [
            org.model_copy(update={"role": self.role_in(actor, org.id)})
            for org in organizations
        ]

    def require_access(self, actor: Actor, organization_id: str) -> None:
        """Raise when an actor cannot access a tenant."""
        if organization_id not in actor.organization_ids:
            raise api_error(
                status_code=403,
                code="forbidden",
                message="Caller does not have access to this organization",
                details={"organization_id": organization_id},
            )

    def role_in(self, actor: Actor, organization_id: str) -> OrgRole | None:
        value = actor.roles.get(organization_id)
        try:
            return OrgRole(value) if value is not None else None
        except ValueError:
            return None

    def workspace_access(
        self, actor: Actor, organization_id: str
    ) -> WorkspaceAccess | None:
        """What the actor's organization role grants over the org's own workspaces.

        An actor without a role for the org (unscoped dev tokens) keeps the
        original behaviour: every member is an owner.
        """
        if organization_id not in actor.organization_ids:
            return None
        if organization_id not in actor.roles:
            return "owner"
        role = self.role_in(actor, organization_id)
        return WORKSPACE_ACCESS.get(role) if role is not None else None

    def require_write(self, actor: Actor, organization_id: str) -> None:
        """Require a role that may create and change data in the organization."""
        self.require_access(actor, organization_id)
        if self.workspace_access(actor, organization_id) not in ("owner", "editor"):
            raise _forbidden(
                "Your role in this organization is read-only",
                organization_id=organization_id,
            )

    def require_permission(
        self, actor: Actor, organization_id: str, permission: str
    ) -> None:
        """Require an org-level permission granted by the actor's role."""
        self.require_access(actor, organization_id)
        if organization_id not in actor.roles:
            return
        role = self.role_in(actor, organization_id)
        if role is None or permission not in ROLE_PERMISSIONS[role]:
            raise _forbidden(
                "Your role in this organization does not allow this action",
                organization_id=organization_id,
                required_permission=permission,
            )


def _unverified_jwt_enabled() -> bool:
    """Whether unverified JWT decoding is explicitly enabled for local dev.

    Fails closed: unless HELIX_ALLOW_UNVERIFIED_JWT=1 is set in a development
    environment, unsigned tokens are never accepted. Hosted environments ignore
    the flag (and refuse to start with it set).
    """
    return config.unverified_jwt_enabled()


def _decode_unverified_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode a JWT-like payload without signature verification for local dev."""
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


_verifier: OidcVerifier | None = None


def _oidc_verifier() -> OidcVerifier | None:
    """The shared verifier (its JWKS cache must outlive a request)."""
    global _verifier
    settings = config.oidc_settings()
    if settings is None:
        _verifier = None
        return None
    if _verifier is None or _verifier.settings != settings:
        _verifier = OidcVerifier(settings)
    return _verifier


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def _actor_from_oidc(token: str, verifier: OidcVerifier) -> Actor | None:
    try:
        claims = verifier.verify(token)
    except OidcError as error:
        if error.unavailable:
            logger.error(
                "identity provider unreachable", extra={"reason": error.reason}
            )
            raise api_error(
                status_code=503,
                code="auth_unavailable",
                message="Authentication is temporarily unavailable; retry shortly",
            ) from None
        logger.info("token rejected", extra={"reason": error.reason})
        return None

    settings = verifier.settings
    email = claims.get(settings.email_claim)
    name = claims.get(settings.name_claim)
    identity = auth_store.resolve_identity(
        issuer=settings.issuer,
        subject=claims["sub"],
        email=email.strip().lower()
        if isinstance(email, str) and email.strip()
        else None,
        email_verified=_truthy(claims.get("email_verified")),
        display_name=name.strip()[:200]
        if isinstance(name, str) and name.strip()
        else None,
    )
    if not identity.is_active:
        raise api_error(
            status_code=403,
            code="account_disabled",
            message="This account has been disabled",
        )

    roles = {
        org_id: role
        for org_id, role in identity.roles.items()
        if role in {item.value for item in OrgRole}
    }
    return Actor(
        subject=identity.user_id,
        organization_ids=[
            org_id for org_id, role in roles.items() if role != OrgRole.EXTERNAL.value
        ],
        permissions=permissions_for(roles),
        email=identity.email,
        roles=roles,
    )


def actor_from_token(token: str) -> Actor | None:
    """Resolve an actor from a bearer token, or ``None`` when it is not valid."""
    if config.demo_tokens_enabled() and token in DEMO_TOKENS:
        return DEMO_TOKENS[token]

    if _unverified_jwt_enabled():
        actor = _actor_from_unverified_jwt(token)
        if actor is not None:
            return actor

    verifier = _oidc_verifier()
    if verifier is not None:
        return _actor_from_oidc(token, verifier)
    return None


def _actor_from_unverified_jwt(token: str) -> Actor | None:
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


def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Actor:
    """Extract the authenticated actor from a bearer token."""
    if credentials is None:
        raise api_error(
            status_code=401, code="unauthorized", message="Bearer token is required"
        )

    actor = actor_from_token(credentials.credentials)
    if actor is None:
        raise api_error(
            status_code=401, code="unauthorized", message="Bearer token is invalid"
        )
    bind(actor=actor.subject)
    return actor


organization_service = OrganizationService()
