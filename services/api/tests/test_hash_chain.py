"""Hash-chain audit storage tests."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from helixos.audit.hash_chain import canonical_timestamp, compute_event_hash, verify_chain
from helixos.audit.memory_store import MemoryAuditStore
from helixos.audit.service import AuditService, build_audit_store
from helixos.auth.schemas import Actor
from helixos.main import create_app

ORG_DEMO_HEADERS = {"Authorization": "Bearer org-demo-token"}
ACTOR = Actor(subject="user_demo_scientist", organization_ids=["org_demo"])


def test_memory_store_builds_valid_hash_chain() -> None:
    store = MemoryAuditStore()
    store.append(
        organization_id="org_demo",
        actor_subject="user_demo_scientist",
        event_type="ai.run_started",
        payload={"run_id": "run_1"},
    )
    store.append(
        organization_id="org_demo",
        actor_subject="user_demo_scientist",
        event_type="ai.run_completed",
        payload={"run_id": "run_1"},
    )

    verification = store.verify_chain("org_demo")
    assert verification.valid is True
    assert verification.event_count == 2
    assert verification.head_hash is not None


def test_sqlite_store_persists_hash_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "audit.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("HELIX_DATABASE_URL", database_url)

    from helixos.db.session import reset_engine

    reset_engine()
    service = AuditService(store=build_audit_store())
    service.record(
        organization_id="org_demo",
        actor=ACTOR,
        event_type="ai.session_created",
        resource_type="agent_session",
        resource_id="sess_1",
    )
    service.record(
        organization_id="org_demo",
        actor=ACTOR,
        event_type="ai.tool_call",
        resource_type="agent_run",
        resource_id="run_1",
        payload={"tool": "list_experiments"},
    )

    verification = service.verify_chain(ACTOR, "org_demo")
    assert verification.valid is True
    assert verification.event_count == 2

    reloaded = AuditService(store=build_audit_store())
    events = reloaded.list_for_actor(ACTOR, organization_id="org_demo")
    assert len(events) == 2
    assert events[0].event_hash is not None
    assert events[0].sequence_number == 2


def test_verify_audit_chain_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "audit-api.db"
    monkeypatch.setenv("HELIX_DATABASE_URL", f"sqlite:///{db_path}")

    from helixos.db.session import reset_engine

    reset_engine()
    client = TestClient(create_app())
    session_response = client.post(
        "/api/v1/ai/sessions",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo"},
    )
    session_id = session_response.json()["id"]

    with client.stream(
        "POST",
        "/api/v1/ai/runs",
        headers=ORG_DEMO_HEADERS,
        json={"session_id": session_id, "message": "Summarize", "context": {}},
    ) as response:
        response.read()

    verify_response = client.get(
        "/api/v1/audit/verify",
        headers=ORG_DEMO_HEADERS,
        params={"organization_id": "org_demo"},
    )
    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["valid"] is True
    assert body["event_count"] >= 4


def test_canonical_timestamp_normalizes_naive_utc() -> None:
    aware = datetime(2026, 6, 7, 10, 18, 47, 143864, tzinfo=timezone.utc)
    naive = datetime(2026, 6, 7, 10, 18, 47, 143864)
    assert canonical_timestamp(aware) == canonical_timestamp(naive)


def test_compute_event_hash_is_deterministic() -> None:
    created_at = datetime(2026, 6, 7, tzinfo=timezone.utc)
    first = compute_event_hash(
        id="audit_1",
        organization_id="org_demo",
        actor_subject="user",
        event_type="ai.run_started",
        resource_type="agent_run",
        resource_id="run_1",
        payload={"run_id": "run_1"},
        previous_hash=None,
        created_at=created_at,
        sequence_number=1,
        chain_scope="org_demo",
    )
    second = compute_event_hash(
        id="audit_1",
        organization_id="org_demo",
        actor_subject="user",
        event_type="ai.run_started",
        resource_type="agent_run",
        resource_id="run_1",
        payload={"run_id": "run_1"},
        previous_hash=None,
        created_at=created_at,
        sequence_number=1,
        chain_scope="org_demo",
    )
    assert first == second

    tampered = verify_chain(
        [
            {
                "id": "audit_1",
                "organization_id": "org_demo",
                "actor_subject": "user",
                "event_type": "ai.run_started",
                "resource_type": "agent_run",
                "resource_id": "run_1",
                "payload": {"run_id": "run_1"},
                "previous_hash": None,
                "event_hash": "deadbeef",
                "created_at": created_at,
                "sequence_number": 1,
                "chain_scope": "org_demo",
            }
        ]
    )
    assert tampered.valid is False
