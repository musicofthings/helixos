"""Audit event API routes."""

from fastapi import APIRouter, Depends, Query

from helixos.audit.schemas import AuditChainVerification, AuditEvent
from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor, organization_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=list[AuditEvent])
def list_audit_events(
    organization_id: str | None = Query(default=None),
    actor: Actor = Depends(get_current_actor),
) -> list[AuditEvent]:
    """List audit events visible to the authenticated caller."""
    if organization_id is not None:
        organization_service.require_access(actor, organization_id)
    return audit_service.list_for_actor(actor, organization_id=organization_id)


@router.get("/verify", response_model=AuditChainVerification)
def verify_audit_chain(
    organization_id: str = Query(...),
    actor: Actor = Depends(get_current_actor),
) -> AuditChainVerification:
    """Verify the hash chain for an organization audit log."""
    return audit_service.verify_chain(actor, organization_id)
