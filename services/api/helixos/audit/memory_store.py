"""In-memory audit store for tests and local development."""

from helixos.audit.hash_chain import canonical_payload, compute_event_hash, verify_chain
from helixos.audit.models import AuditEventRecord
from helixos.audit.schemas import AuditChainVerification, AuditEvent
from helixos.auth.schemas import Actor


class MemoryAuditStore:
    """Append-only in-memory audit store with hash chaining."""

    def __init__(self) -> None:
        self._events: list[AuditEventRecord] = []
        self._sequence_by_org: dict[str, int] = {}

    def append(
        self,
        *,
        organization_id: str,
        actor_subject: str,
        event_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> AuditEventRecord:
        sequence_number = self._sequence_by_org.get(organization_id, 0) + 1
        previous_hash = self._head_hash(organization_id)
        event = AuditEventRecord.create(
            organization_id=organization_id,
            actor_subject=actor_subject,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=dict(payload or {}),
        )
        event_hash = compute_event_hash(
            id=event.id,
            organization_id=event.organization_id,
            actor_subject=event.actor_subject,
            event_type=event.event_type,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            payload=event.payload,
            previous_hash=previous_hash,
            created_at=event.created_at,
            sequence_number=sequence_number,
            chain_scope=organization_id,
        )
        stored = AuditEventRecord(
            id=event.id,
            organization_id=event.organization_id,
            actor_subject=event.actor_subject,
            event_type=event.event_type,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            payload=event.payload,
            created_at=event.created_at,
            previous_hash=previous_hash,
            event_hash=event_hash,
            sequence_number=sequence_number,
            chain_scope=organization_id,
            payload_digest=canonical_payload(event.payload),
        )
        self._events.append(stored)
        self._sequence_by_org[organization_id] = sequence_number
        return stored

    def list_for_actor(self, actor: Actor, organization_id: str | None = None) -> list[AuditEvent]:
        visible_orgs = set(actor.organization_ids)
        events = [
            event
            for event in self._events
            if event.organization_id in visible_orgs
            and (organization_id is None or event.organization_id == organization_id)
        ]
        events.sort(key=lambda item: item.created_at, reverse=True)
        return [self._to_schema(event) for event in events]

    def verify_chain(self, organization_id: str) -> AuditChainVerification:
        events = [
            self._event_dict(event)
            for event in sorted(
                (item for item in self._events if item.organization_id == organization_id),
                key=lambda item: item.sequence_number,
            )
        ]
        result = verify_chain(events)
        return AuditChainVerification(
            organization_id=result.organization_id,
            valid=result.valid,
            event_count=result.event_count,
            head_hash=result.head_hash,
            message=result.message,
        )

    def _head_hash(self, organization_id: str) -> str | None:
        org_events = [event for event in self._events if event.organization_id == organization_id]
        if not org_events:
            return None
        return max(org_events, key=lambda item: item.sequence_number).event_hash

    @staticmethod
    def _to_schema(event: AuditEventRecord) -> AuditEvent:
        return AuditEvent(
            id=event.id,
            organization_id=event.organization_id,
            actor_subject=event.actor_subject,
            event_type=event.event_type,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            payload=event.payload,
            created_at=event.created_at,
            previous_hash=event.previous_hash,
            event_hash=event.event_hash,
            sequence_number=event.sequence_number,
        )

    @staticmethod
    def _event_dict(event: AuditEventRecord) -> dict[str, object]:
        return {
            "id": event.id,
            "organization_id": event.organization_id,
            "actor_subject": event.actor_subject,
            "event_type": event.event_type,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "payload": event.payload,
            "previous_hash": event.previous_hash,
            "event_hash": event.event_hash,
            "created_at": event.created_at,
            "sequence_number": event.sequence_number,
            "chain_scope": event.chain_scope,
        }
