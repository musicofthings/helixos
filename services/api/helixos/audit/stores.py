"""Audit storage backends."""

from __future__ import annotations

from typing import Protocol

from helixos.audit.models import AuditEventRecord
from helixos.audit.schemas import AuditEvent, AuditChainVerification
from helixos.auth.schemas import Actor


class AuditStore(Protocol):
    """Persistence contract for audit events."""

    def append(
        self,
        *,
        organization_id: str,
        actor_subject: str,
        event_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> AuditEventRecord: ...

    def list_for_actor(self, actor: Actor, organization_id: str | None = None) -> list[AuditEvent]: ...

    def verify_chain(self, organization_id: str) -> AuditChainVerification: ...
