"""Organization API routes."""

from fastapi import APIRouter, Depends

from helixos.auth.schemas import Actor, Organization
from helixos.auth.service import get_current_actor, organization_service

router = APIRouter(prefix="/organizations", tags=["auth"])


@router.get("", response_model=list[Organization])
def list_organizations(actor: Actor = Depends(get_current_actor)) -> list[Organization]:
    """List organizations visible to the authenticated caller."""
    return organization_service.list_for_actor(actor)
