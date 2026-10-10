"""Regression tests for review findings: collaborator writes, atomic invite
acceptance, and compare-and-swap version transitions."""

import pytest
from fastapi.testclient import TestClient

from helixos.eln.schemas import ExperimentStatus
from helixos.eln.service import eln_service
from helixos.eln.stores import InviteUnavailableError, StaleStateError

ORG_DEMO = {"Authorization": "Bearer org-demo-token"}
ADMIN = {"Authorization": "Bearer demo-admin-token"}
CLIENT_FIXTURES = ["memory_client", "sqlite_client"]


@pytest.fixture
def client(request) -> TestClient:
    return request.getfixturevalue(request.param)


def _qc_workspace(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/workspaces",
        headers=ADMIN,
        json={"organization_id": "org_qc", "name": "QC", "category": "custom"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _invite(client: TestClient, workspace_id: str, **body) -> str:
    payload = {"role": "editor", "expires_in_hours": 24, **body}
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/invites", headers=ADMIN, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_cross_org_editor_can_create_project_and_audit_is_recorded(client) -> None:
    workspace = _qc_workspace(client)
    token = _invite(client, workspace["id"], role="editor")
    accepted = client.post(f"/api/v1/workspace-invites/{token}/accept", headers=ORG_DEMO)
    assert accepted.status_code == 201, accepted.text

    created = client.post(
        "/api/v1/projects",
        headers=ORG_DEMO,
        json={
            "organization_id": "org_qc",
            "workspace_id": workspace["id"],
            "name": "Editor project",
        },
    )
    assert created.status_code == 201, created.text

    events = client.get("/api/v1/audit/events?organization_id=org_qc", headers=ADMIN).json()
    assert any(
        e["event_type"] == "eln.project_created"
        and e["actor_subject"] == "user_demo_scientist"
        for e in events
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_invite_max_uses_enforced_against_stale_snapshots(client) -> None:
    workspace = _qc_workspace(client)
    token = _invite(client, workspace["id"], role="viewer", max_uses=1)
    store = eln_service._store

    first = store.get_invite_by_token(token)
    second = store.get_invite_by_token(token)  # same snapshot, accepted_count == 0
    assert first is not None and second is not None

    store.accept_invite(first, None)
    with pytest.raises(InviteUnavailableError):
        store.accept_invite(second, None)
    assert store.get_invite(first.id).accepted_count == 1


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_revoked_invite_cannot_be_accepted_from_stale_snapshot(client) -> None:
    workspace = _qc_workspace(client)
    token = _invite(client, workspace["id"], role="viewer")
    store = eln_service._store
    stale = store.get_invite_by_token(token)
    store.update_invite(stale.model_copy(update={"revoked_at": stale.created_at}))
    with pytest.raises(InviteUnavailableError):
        store.accept_invite(stale, None)


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_version_status_update_is_compare_and_swap(client) -> None:
    experiment = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO,
        json={"organization_id": "org_demo", "name": "CAS", "blocks": []},
    ).json()
    store = eln_service._store
    version = store.list_versions(experiment["id"])[0]
    in_review = version.model_copy(update={"status": ExperimentStatus.IN_REVIEW})
    store.update_version(in_review, expected_status=ExperimentStatus.DRAFT)

    signed = in_review.model_copy(update={"status": ExperimentStatus.SIGNED})
    store.update_version(signed, expected_status=ExperimentStatus.IN_REVIEW)

    # A request holding the stale in_review snapshot must not unlock the signature.
    rollback = in_review.model_copy(update={"status": ExperimentStatus.DRAFT})
    with pytest.raises(StaleStateError):
        store.update_version(rollback, expected_status=ExperimentStatus.IN_REVIEW)
    assert store.get_version(version.id).status == ExperimentStatus.SIGNED


def test_audit_failure_rolls_back_mutation_on_sql_store(sqlite_client, monkeypatch) -> None:
    from helixos.audit.service import audit_service

    workspace = sqlite_client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO,
        json={"organization_id": "org_demo", "name": "Atomic", "category": "custom"},
    ).json()

    def boom(**_kwargs):
        raise ValueError("audit store unavailable")

    with monkeypatch.context() as scoped:
        scoped.setattr(audit_service._store, "append", boom)
        failing = TestClient(sqlite_client.app, raise_server_exceptions=False)
        response = failing.post(
            "/api/v1/projects",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "workspace_id": workspace["id"],
                "name": "Should not persist",
            },
        )
    assert response.status_code == 500

    listed = sqlite_client.get(
        f"/api/v1/projects?workspace_id={workspace['id']}", headers=ORG_DEMO
    ).json()
    assert [p["name"] for p in listed] == []


def test_concurrent_creates_all_commit_with_audit_events(sqlite_client) -> None:
    from concurrent.futures import ThreadPoolExecutor

    workspace = sqlite_client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO,
        json={"organization_id": "org_demo", "name": "Burst", "category": "custom"},
    ).json()

    def create(i: int) -> int:
        return sqlite_client.post(
            "/api/v1/projects",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "workspace_id": workspace["id"],
                "name": f"p{i}",
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(create, range(16)))
    assert codes == [201] * 16

    events = sqlite_client.get(
        "/api/v1/audit/events?organization_id=org_demo&limit=200", headers=ORG_DEMO
    ).json()
    assert sum(e["event_type"] == "eln.project_created" for e in events) == 16
    verification = sqlite_client.get(
        "/api/v1/audit/verify?organization_id=org_demo", headers=ORG_DEMO
    )
    if verification.status_code == 200:
        assert verification.json()["valid"] is True
