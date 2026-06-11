"""Audit event recording and retrieval."""

from helixos.audit.memory_store import MemoryAuditStore
from helixos.audit.models import AuditEventRecord
from helixos.audit.schemas import AuditChainVerification, AuditEvent
from helixos.audit.sql_store import SqlAuditStore
from helixos.audit.stores import AuditStore
from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.db.session import init_db
from helixos.db.settings import DatabaseSettings, get_database_settings


def build_audit_store(settings: DatabaseSettings | None = None) -> AuditStore:
    """Create the configured audit store backend."""
    resolved = settings or get_database_settings()
    if resolved.is_configured:
        init_db(resolved)
        return SqlAuditStore()
    return MemoryAuditStore()


class AuditService:
    """Coordinates immutable audit event storage."""

    def __init__(self, store: AuditStore | None = None) -> None:
        self._store = store or build_audit_store()

    def use_store(self, store: AuditStore) -> None:
        """Replace the active audit store backend."""
        self._store = store

    def record(
        self,
        *,
        organization_id: str,
        actor: Actor,
        event_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> AuditEventRecord:
        """Persist an audit event for a regulated action."""
        organization_service.require_access(actor, organization_id)
        return self._store.append(
            organization_id=organization_id,
            actor_subject=actor.subject,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=dict(payload or {}),
        )

    def record_system(
        self,
        *,
        organization_id: str,
        actor_subject: str,
        event_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> AuditEventRecord:
        """Persist an audit event without actor access checks (internal use)."""
        return self._store.append(
            organization_id=organization_id,
            actor_subject=actor_subject,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=dict(payload or {}),
        )

    def list_for_actor(self, actor: Actor, organization_id: str | None = None) -> list[AuditEvent]:
        """List audit events visible to the authenticated actor."""
        return self._store.list_for_actor(actor, organization_id=organization_id)

    def verify_chain(self, actor: Actor, organization_id: str) -> AuditChainVerification:
        """Verify the hash chain for an organization."""
        organization_service.require_access(actor, organization_id)
        return self._store.verify_chain(organization_id)


audit_service = AuditService()
