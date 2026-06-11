"""Hash-chain helpers for immutable audit events."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def canonical_timestamp(value: datetime) -> str:
    """Return a stable UTC timestamp string for hash computation."""
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=timezone.utc)
    else:
        normalized = value.astimezone(timezone.utc)
    text = normalized.isoformat()
    if text.endswith("+00:00"):
        return f"{text[:-6]}Z"
    return text


def canonical_payload(payload: dict[str, Any]) -> str:
    """Return a stable JSON representation for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(
    *,
    id: str,
    organization_id: str,
    actor_subject: str,
    event_type: str,
    resource_type: str | None,
    resource_id: str | None,
    payload: dict[str, Any],
    previous_hash: str | None,
    created_at: datetime,
    sequence_number: int,
    chain_scope: str,
) -> str:
    """Compute the SHA-256 hash for an audit event."""
    digest_input = {
        "id": id,
        "organization_id": organization_id,
        "actor_subject": actor_subject,
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "payload": payload,
        "previous_hash": previous_hash,
        "created_at": canonical_timestamp(created_at),
        "sequence_number": sequence_number,
        "chain_scope": chain_scope,
    }
    encoded = json.dumps(digest_input, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ChainVerificationResult:
    """Outcome of verifying an organization audit chain."""

    organization_id: str
    valid: bool
    event_count: int
    head_hash: str | None
    message: str


def verify_chain(events: list[dict[str, Any]]) -> ChainVerificationResult:
    """Verify a sequence of audit events ordered oldest to newest."""
    if not events:
        organization_id = "unknown"
        return ChainVerificationResult(
            organization_id=organization_id,
            valid=True,
            event_count=0,
            head_hash=None,
            message="No events to verify",
        )

    organization_id = str(events[0]["organization_id"])
    previous_hash: str | None = None

    for index, event in enumerate(events):
        expected_sequence = index + 1
        if event.get("sequence_number") != expected_sequence:
            return ChainVerificationResult(
                organization_id=organization_id,
                valid=False,
                event_count=len(events),
                head_hash=previous_hash,
                message=f"Sequence gap at event {event.get('id')}",
            )

        computed = compute_event_hash(
            id=str(event["id"]),
            organization_id=str(event["organization_id"]),
            actor_subject=str(event["actor_subject"]),
            event_type=str(event["event_type"]),
            resource_type=event.get("resource_type"),
            resource_id=event.get("resource_id"),
            payload=dict(event.get("payload") or {}),
            previous_hash=previous_hash,
            created_at=event["created_at"],
            sequence_number=int(event["sequence_number"]),
            chain_scope=str(event.get("chain_scope") or organization_id),
        )

        if event.get("previous_hash") != previous_hash:
            return ChainVerificationResult(
                organization_id=organization_id,
                valid=False,
                event_count=len(events),
                head_hash=previous_hash,
                message=f"Previous hash mismatch at event {event.get('id')}",
            )

        if event.get("event_hash") != computed:
            return ChainVerificationResult(
                organization_id=organization_id,
                valid=False,
                event_count=len(events),
                head_hash=previous_hash,
                message=f"Event hash mismatch at event {event.get('id')}",
            )

        previous_hash = str(event["event_hash"])

    return ChainVerificationResult(
        organization_id=organization_id,
        valid=True,
        event_count=len(events),
        head_hash=previous_hash,
        message="Audit chain verified",
    )
