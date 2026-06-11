"""In-memory audit event records."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AuditEventRecord:
    """Immutable audit event stored by the starter kit."""

    id: str
    organization_id: str
    actor_subject: str
    event_type: str
    resource_type: str | None
    resource_id: str | None
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    previous_hash: str | None = None
    event_hash: str | None = None
    sequence_number: int = 0
    chain_scope: str | None = None
    payload_digest: str | None = None

    @classmethod
    def create(
        cls,
        *,
        organization_id: str,
        actor_subject: str,
        event_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "AuditEventRecord":
        return cls(
            id=f"audit_{uuid4().hex}",
            organization_id=organization_id,
            actor_subject=actor_subject,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload or {},
        )
