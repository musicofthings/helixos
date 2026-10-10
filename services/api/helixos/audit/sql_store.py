"""SQL-backed audit store for Postgres and SQLite."""

from __future__ import annotations

import random
import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from helixos.audit.hash_chain import canonical_payload, compute_event_hash, verify_chain
from helixos.audit.models import AuditEventRecord
from helixos.audit.orm import AuditEventORM
from helixos.audit.schemas import AuditChainVerification, AuditEvent
from helixos.auth.schemas import Actor
from helixos.db.session import in_unit_of_work, session_scope

# SQLite serializes writes, so bursts of concurrent audit appends contend on
# both the write lock and the (organization_id, sequence_number) unique index.
# Retry with exponential backoff + jitter so colliding writers desynchronize
# instead of lockstepping through their attempts.
_APPEND_MAX_ATTEMPTS = 12
_APPEND_BACKOFF_BASE_SECONDS = 0.01
_APPEND_BACKOFF_MAX_SECONDS = 0.25


class SqlAuditStore:
    """Persist audit events in Postgres or SQLite with hash chaining."""

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
        # Concurrent appends for the same organization can read the same chain
        # head and collide on (organization_id, sequence_number). The unique
        # constraint turns that into an IntegrityError; a busy SQLite writer
        # surfaces as OperationalError. Both are transient — retry re-reads the
        # head and recomputes the hash.
        if in_unit_of_work():
            # A conflict poisons the shared transaction; the owner retries it whole.
            return self._append_once(
                organization_id=organization_id,
                actor_subject=actor_subject,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=dict(payload or {}),
            )
        last_error: Exception | None = None
        for attempt in range(_APPEND_MAX_ATTEMPTS):
            try:
                return self._append_once(
                    organization_id=organization_id,
                    actor_subject=actor_subject,
                    event_type=event_type,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    payload=dict(payload or {}),
                )
            except (IntegrityError, OperationalError) as exc:
                last_error = exc
                backoff = min(
                    _APPEND_BACKOFF_BASE_SECONDS * (2**attempt),
                    _APPEND_BACKOFF_MAX_SECONDS,
                )
                time.sleep(random.uniform(0, backoff))
                continue
        raise RuntimeError("Failed to append audit event after retries") from last_error

    def _append_once(
        self,
        *,
        organization_id: str,
        actor_subject: str,
        event_type: str,
        resource_type: str | None,
        resource_id: str | None,
        payload: dict[str, object],
    ) -> AuditEventRecord:
        event = AuditEventRecord.create(
            organization_id=organization_id,
            actor_subject=actor_subject,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
        )

        with session_scope() as session:
            previous_hash, sequence_number = self._next_chain_state(
                session, organization_id
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
            row = AuditEventORM(
                id=event.id,
                organization_id=event.organization_id,
                actor_subject=event.actor_subject,
                event_type=event.event_type,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                payload=event.payload,
                previous_hash=previous_hash,
                event_hash=event_hash,
                created_at=event.created_at,
                chain_scope=organization_id,
                sequence_number=sequence_number,
                payload_digest=canonical_payload(event.payload),
            )
            session.add(row)
            session.flush()
            return AuditEventRecord(
                id=row.id,
                organization_id=row.organization_id,
                actor_subject=row.actor_subject,
                event_type=row.event_type,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                payload=row.payload,
                created_at=row.created_at,
                previous_hash=row.previous_hash,
                event_hash=row.event_hash,
                sequence_number=row.sequence_number,
                chain_scope=row.chain_scope,
                payload_digest=row.payload_digest,
            )

    def list_for_actor(
        self, actor: Actor, organization_id: str | None = None, limit: int = 50
    ) -> list[AuditEvent]:
        visible_orgs = set(actor.organization_ids)
        with session_scope() as session:
            query = select(AuditEventORM).where(
                AuditEventORM.organization_id.in_(visible_orgs)
            )
            if organization_id is not None:
                query = query.where(AuditEventORM.organization_id == organization_id)
            query = query.order_by(AuditEventORM.created_at.desc()).limit(limit)
            rows = session.scalars(query).all()
            return [self._to_schema(row) for row in rows]

    def verify_chain(self, organization_id: str) -> AuditChainVerification:
        with session_scope() as session:
            rows = session.scalars(
                select(AuditEventORM)
                .where(AuditEventORM.organization_id == organization_id)
                .order_by(AuditEventORM.sequence_number.asc())
            ).all()
            events = [self._row_dict(row) for row in rows]
        result = verify_chain(events)
        return AuditChainVerification(
            organization_id=result.organization_id,
            valid=result.valid,
            event_count=result.event_count,
            head_hash=result.head_hash,
            message=result.message,
        )

    @staticmethod
    def _next_chain_state(session, organization_id: str) -> tuple[str | None, int]:
        row = session.scalar(
            select(AuditEventORM)
            .where(AuditEventORM.organization_id == organization_id)
            .order_by(AuditEventORM.sequence_number.desc())
            .limit(1)
        )
        if row is None:
            return None, 1
        return row.event_hash, row.sequence_number + 1

    @staticmethod
    def _to_schema(row: AuditEventORM) -> AuditEvent:
        return AuditEvent(
            id=row.id,
            organization_id=row.organization_id,
            actor_subject=row.actor_subject,
            event_type=row.event_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            payload=row.payload,
            created_at=row.created_at,
            previous_hash=row.previous_hash,
            event_hash=row.event_hash,
            sequence_number=row.sequence_number,
        )

    @staticmethod
    def _row_dict(row: AuditEventORM) -> dict[str, object]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "actor_subject": row.actor_subject,
            "event_type": row.event_type,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "payload": row.payload,
            "previous_hash": row.previous_hash,
            "event_hash": row.event_hash,
            "created_at": row.created_at,
            "sequence_number": row.sequence_number,
            "chain_scope": row.chain_scope,
        }
