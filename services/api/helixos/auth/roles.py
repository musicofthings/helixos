"""Organization roles and what they may do.

A role is held per organization (a user can be a scientist in one org and an
external collaborator in another). ``WORKSPACE_ACCESS`` maps a role onto the
workspace policy the ELN already enforces; ``ROLE_PERMISSIONS`` covers the
org-level actions that are not workspace access.
"""

from enum import Enum
from typing import Literal


class OrgRole(str, Enum):
    ADMIN = "admin"
    PI = "pi"
    SCIENTIST = "scientist"
    TECHNICIAN = "technician"
    QA_REVIEWER = "qa_reviewer"
    EXTERNAL = "external_collaborator"


WorkspaceAccess = Literal["owner", "editor", "viewer"]

# Org members' reach over the org's own workspaces. External collaborators are
# deliberately absent: they see only what is explicitly shared with them.
WORKSPACE_ACCESS: dict[OrgRole, WorkspaceAccess] = {
    OrgRole.ADMIN: "owner",
    OrgRole.PI: "owner",
    OrgRole.SCIENTIST: "owner",
    OrgRole.TECHNICIAN: "editor",
    OrgRole.QA_REVIEWER: "viewer",
}

MEMBERS_MANAGE = "members:manage"
EXPERIMENTS_SIGN = "experiments:sign"

ROLE_PERMISSIONS: dict[OrgRole, frozenset[str]] = {
    OrgRole.ADMIN: frozenset({MEMBERS_MANAGE, EXPERIMENTS_SIGN}),
    OrgRole.PI: frozenset({EXPERIMENTS_SIGN}),
    OrgRole.SCIENTIST: frozenset({EXPERIMENTS_SIGN}),
    OrgRole.TECHNICIAN: frozenset(),
    OrgRole.QA_REVIEWER: frozenset({EXPERIMENTS_SIGN}),
    OrgRole.EXTERNAL: frozenset(),
}


def parse_role(value: str) -> OrgRole:
    try:
        return OrgRole(value)
    except ValueError:
        raise ValueError(
            f"Unknown role {value!r}; expected one of "
            + ", ".join(role.value for role in OrgRole)
        ) from None


def permissions_for(roles: dict[str, str]) -> list[str]:
    """Flat, sorted union of permissions across an actor's roles."""
    granted: set[str] = set()
    for value in roles.values():
        granted |= ROLE_PERMISSIONS.get(OrgRole(value), frozenset())
    return sorted(granted)
