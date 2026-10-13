"""Organization API routes."""

from fastapi import APIRouter, Depends, Response

from helixos.auth.members import member_service
from helixos.auth.schemas import (
    Actor,
    MemberAddRequest,
    MemberAddResult,
    MemberRoleUpdate,
    Organization,
    OrgMember,
    OrgMembers,
)
from helixos.auth.service import get_current_actor, organization_service

router = APIRouter(prefix="/organizations", tags=["auth"])


@router.get("", response_model=list[Organization])
def list_organizations(actor: Actor = Depends(get_current_actor)) -> list[Organization]:
    """List organizations visible to the authenticated caller."""
    return organization_service.list_for_actor(actor)


@router.get("/{organization_id}/members", response_model=OrgMembers)
def list_members(
    organization_id: str, actor: Actor = Depends(get_current_actor)
) -> OrgMembers:
    """Members and pending invites of an organization."""
    return member_service.list(organization_id, actor)


@router.post(
    "/{organization_id}/members", response_model=MemberAddResult, status_code=201
)
def add_member(
    organization_id: str,
    payload: MemberAddRequest,
    actor: Actor = Depends(get_current_actor),
) -> MemberAddResult:
    """Add a known user, or invite an email address (admin only)."""
    return member_service.add(organization_id, payload, actor)


@router.patch("/{organization_id}/members/{user_id}", response_model=OrgMember)
def change_member_role(
    organization_id: str,
    user_id: str,
    payload: MemberRoleUpdate,
    actor: Actor = Depends(get_current_actor),
) -> OrgMember:
    """Change a member's role (admin only)."""
    return member_service.set_role(organization_id, user_id, payload.role, actor)


@router.delete("/{organization_id}/members/{user_id}", status_code=204)
def remove_member(
    organization_id: str, user_id: str, actor: Actor = Depends(get_current_actor)
) -> Response:
    """Remove a member (admin only); the last admin cannot be removed."""
    member_service.remove(organization_id, user_id, actor)
    return Response(status_code=204)


@router.delete("/{organization_id}/member-invites/{invite_id}", status_code=204)
def revoke_member_invite(
    organization_id: str, invite_id: str, actor: Actor = Depends(get_current_actor)
) -> Response:
    """Revoke a pending membership invite (admin only)."""
    member_service.revoke_invite(organization_id, invite_id, actor)
    return Response(status_code=204)
