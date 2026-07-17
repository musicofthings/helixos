"""Tests for the ELN hierarchy: workspaces, projects, experiments, versions,
samples (96-well constraints), and datasets.

Each test is parametrized across the in-memory and SQLite-backed clients so the
storage contract is verified for both backends.
"""

import pytest
from fastapi.testclient import TestClient

ORG_DEMO_HEADERS = {"Authorization": "Bearer org-demo-token"}
ADMIN_HEADERS = {"Authorization": "Bearer demo-admin-token"}

CLIENT_FIXTURES = ["memory_client", "sqlite_client"]


@pytest.fixture
def client(request) -> TestClient:
    return request.getfixturevalue(request.param)


def _create_experiment(
    client: TestClient, *, name: str = "CRISPR knockout", project_id: str | None = None
) -> dict:
    payload = {"organization_id": "org_demo", "name": name, "blocks": []}
    if project_id is not None:
        payload["project_id"] = project_id
    response = client.post(
        "/api/v1/experiments", headers=ORG_DEMO_HEADERS, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_seed_default_workspaces_is_idempotent(client: TestClient) -> None:
    first = client.post(
        "/api/v1/workspaces/seed-defaults",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo"},
    )
    assert first.status_code == 200
    categories = {ws["category"] for ws in first.json()}
    assert {"molecular_biology", "biochemistry", "microbiology"}.issubset(categories)
    assert all(ws["is_default"] for ws in first.json())

    second = client.post(
        "/api/v1/workspaces/seed-defaults",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo"},
    )
    assert second.status_code == 200
    listed = client.get(
        "/api/v1/workspaces?organization_id=org_demo", headers=ORG_DEMO_HEADERS
    )
    assert len(listed.json()) == len(first.json())


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_workspace_stores_category_and_subcategory(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "name": "Sequencing core",
            "category": "next_gen_sequencing",
            "subcategory": "RNA",
        },
    )
    assert workspace.status_code == 201, workspace.text
    body = workspace.json()
    assert body["category"] == "next_gen_sequencing"
    assert body["subcategory"] == "RNA"

    # Round-trips through the store (matters for the SQLite backend + migration).
    listed = client.get(
        "/api/v1/workspaces?organization_id=org_demo", headers=ORG_DEMO_HEADERS
    ).json()
    assert any(
        ws["id"] == body["id"] and ws["subcategory"] == "RNA" for ws in listed
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_delete_workspace_cascades_the_whole_subtree(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Doomed", "category": "custom"},
    ).json()
    project = client.post(
        "/api/v1/projects",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "workspace_id": workspace["id"],
            "name": "P",
        },
    ).json()
    experiment = _create_experiment(client, project_id=project["id"])
    sample = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment["id"],
            "name": "S1",
            "sample_type": "dna",
        },
    ).json()
    client.post(
        "/api/v1/datasets",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "sample_id": sample["id"],
            "name": "read",
            "dataset_type": "dna_sequence",
        },
    )

    deleted = client.delete(
        f"/api/v1/workspaces/{workspace['id']}", headers=ORG_DEMO_HEADERS
    )
    assert deleted.status_code == 204

    assert (
        client.get(
            f"/api/v1/workspaces/{workspace['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/projects/{project['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/experiments/{experiment['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/samples/{sample['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_delete_project_leaves_workspace_intact(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Keep", "category": "custom"},
    ).json()
    project = client.post(
        "/api/v1/projects",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "workspace_id": workspace["id"],
            "name": "Drop",
        },
    ).json()
    experiment = _create_experiment(client, project_id=project["id"])

    assert (
        client.delete(
            f"/api/v1/projects/{project['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 204
    )
    assert (
        client.get(
            f"/api/v1/experiments/{experiment['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )
    # Workspace survives its project's deletion.
    assert (
        client.get(
            f"/api/v1/workspaces/{workspace['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 200
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_cross_tenant_delete_is_blocked(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ADMIN_HEADERS,
        json={"organization_id": "org_qc", "name": "QC WS", "category": "custom"},
    ).json()
    forbidden = client.delete(
        f"/api/v1/workspaces/{workspace['id']}", headers=ORG_DEMO_HEADERS
    )
    assert forbidden.status_code == 403
    # Still there for the tenant that owns it.
    assert (
        client.get(
            f"/api/v1/workspaces/{workspace['id']}", headers=ADMIN_HEADERS
        ).status_code
        == 200
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_workspace_share_grant_and_revoke(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Shared", "category": "custom"},
    ).json()
    share = client.post(
        f"/api/v1/workspaces/{workspace['id']}/shares",
        headers=ORG_DEMO_HEADERS,
        json={"subject": "scientist@lab.example", "role": "editor"},
    )
    assert share.status_code == 201, share.text
    body = share.json()
    assert body["subject"] == "scientist@lab.example"
    assert body["role"] == "editor"

    listed = client.get(
        f"/api/v1/workspaces/{workspace['id']}/shares", headers=ORG_DEMO_HEADERS
    ).json()
    assert len(listed["shares"]) == 1
    assert listed["invites"] == []

    patched = client.patch(
        f"/api/v1/workspaces/{workspace['id']}/shares/{body['id']}",
        headers=ORG_DEMO_HEADERS,
        json={"role": "viewer"},
    )
    assert patched.status_code == 200
    assert patched.json()["role"] == "viewer"

    invalid_subject = client.post(
        f"/api/v1/workspaces/{workspace['id']}/shares",
        headers=ORG_DEMO_HEADERS,
        json={"subject": "not-a-valid-subject", "role": "viewer"},
    )
    assert invalid_subject.status_code == 422

    dup = client.post(
        f"/api/v1/workspaces/{workspace['id']}/shares",
        headers=ORG_DEMO_HEADERS,
        json={"subject": "scientist@lab.example", "role": "viewer"},
    )
    assert dup.status_code == 409

    revoked = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/shares/{body['id']}",
        headers=ORG_DEMO_HEADERS,
    )
    assert revoked.status_code == 204
    listed_after = client.get(
        f"/api/v1/workspaces/{workspace['id']}/shares", headers=ORG_DEMO_HEADERS
    ).json()
    assert listed_after["shares"] == []


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_workspace_invite_create_accept_and_revoke(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Invite me", "category": "custom"},
    ).json()
    invite = client.post(
        f"/api/v1/workspaces/{workspace['id']}/invites",
        headers=ORG_DEMO_HEADERS,
        json={"role": "viewer", "expires_in_hours": 24, "max_uses": 5},
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["token"]
    assert token
    assert invite.json()["max_uses"] == 5

    # List redacts the capability token.
    collab_before = client.get(
        f"/api/v1/workspaces/{workspace['id']}/shares", headers=ORG_DEMO_HEADERS
    ).json()
    assert collab_before["invites"][0]["token"] is None

    accepted = client.post(
        f"/api/v1/workspace-invites/{token}/accept",
        headers=ORG_DEMO_HEADERS,
    )
    assert accepted.status_code == 201
    assert accepted.json()["subject"] == "user_demo_scientist"
    assert accepted.json()["role"] == "viewer"

    collab = client.get(
        f"/api/v1/workspaces/{workspace['id']}/shares", headers=ORG_DEMO_HEADERS
    ).json()
    assert len(collab["shares"]) == 1
    assert collab["invites"][0]["accepted_count"] == 1
    assert collab["invites"][0]["token"] is None

    # Accepting again is idempotent for the grant.
    again = client.post(
        f"/api/v1/workspace-invites/{token}/accept",
        headers=ORG_DEMO_HEADERS,
    )
    assert again.status_code == 201
    collab2 = client.get(
        f"/api/v1/workspaces/{workspace['id']}/shares", headers=ORG_DEMO_HEADERS
    ).json()
    assert len(collab2["shares"]) == 1
    assert collab2["invites"][0]["accepted_count"] == 2

    revoked = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/invites/{invite.json()['id']}",
        headers=ORG_DEMO_HEADERS,
    )
    assert revoked.status_code == 204
    inactive = client.post(
        f"/api/v1/workspace-invites/{token}/accept",
        headers=ORG_DEMO_HEADERS,
    )
    assert inactive.status_code == 410


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_workspace_delete_cascades_shares_and_invites(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Gone", "category": "custom"},
    ).json()
    share = client.post(
        f"/api/v1/workspaces/{workspace['id']}/shares",
        headers=ORG_DEMO_HEADERS,
        json={"subject": "peer@lab.example", "role": "viewer"},
    )
    assert share.status_code == 201
    invite = client.post(
        f"/api/v1/workspaces/{workspace['id']}/invites",
        headers=ORG_DEMO_HEADERS,
        json={"role": "editor"},
    )
    assert invite.status_code == 201
    assert (
        client.delete(
            f"/api/v1/workspaces/{workspace['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 204
    )
    assert (
        client.get(
            f"/api/v1/workspaces/{workspace['id']}/shares", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/workspace-invites/{invite.json()['token']}/accept",
            headers=ORG_DEMO_HEADERS,
        ).status_code
        == 404
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_cross_tenant_share_is_blocked(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ADMIN_HEADERS,
        json={"organization_id": "org_qc", "name": "QC Share", "category": "custom"},
    ).json()
    forbidden = client.post(
        f"/api/v1/workspaces/{workspace['id']}/shares",
        headers=ORG_DEMO_HEADERS,
        json={"subject": "peer@lab.example", "role": "viewer"},
    )
    assert forbidden.status_code == 403


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_invite_accept_grants_shared_workspace_access(client: TestClient) -> None:
    """Accepting an invite to another org's workspace enables shared-with-me access."""
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ADMIN_HEADERS,
        json={"organization_id": "org_qc", "name": "QC Shared", "category": "custom"},
    ).json()
    project = client.post(
        "/api/v1/projects",
        headers=ADMIN_HEADERS,
        json={
            "organization_id": "org_qc",
            "workspace_id": workspace["id"],
            "name": "QC Project",
        },
    ).json()
    invite = client.post(
        f"/api/v1/workspaces/{workspace['id']}/invites",
        headers=ADMIN_HEADERS,
        json={"role": "viewer", "expires_in_hours": 24},
    ).json()

    # Demo scientist is not an org_qc member until they accept.
    assert (
        client.get(
            f"/api/v1/workspaces/{workspace['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 403
    )

    accepted = client.post(
        f"/api/v1/workspace-invites/{invite['token']}/accept",
        headers=ORG_DEMO_HEADERS,
    )
    assert accepted.status_code == 201

    visible = client.get("/api/v1/workspaces", headers=ORG_DEMO_HEADERS).json()
    assert any(item["id"] == workspace["id"] for item in visible)

    assert (
        client.get(
            f"/api/v1/workspaces/{workspace['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 200
    )
    projects = client.get(
        f"/api/v1/projects?workspace_id={workspace['id']}", headers=ORG_DEMO_HEADERS
    )
    assert projects.status_code == 200
    assert len(projects.json()) == 1

    # Viewer cannot create under the shared workspace.
    create_blocked = client.post(
        "/api/v1/projects",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_qc",
            "workspace_id": workspace["id"],
            "name": "Nope",
        },
    )
    assert create_blocked.status_code == 403

    # Viewer cannot manage shares (owner-only).
    assert (
        client.get(
            f"/api/v1/workspaces/{workspace['id']}/shares", headers=ORG_DEMO_HEADERS
        ).status_code
        == 403
    )
    assert project["id"]  # keep fixture used / silence lint


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_delete_sample_cascades_datasets(client: TestClient) -> None:
    experiment = _create_experiment(client)
    sample = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment["id"],
            "name": "Colony",
            "sample_type": "dna",
            "well_position": "A1",
        },
    ).json()
    dataset = client.post(
        "/api/v1/datasets",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "sample_id": sample["id"],
            "name": "Sanger",
            "dataset_type": "dna_sequence",
        },
    ).json()

    deleted = client.delete(
        f"/api/v1/samples/{sample['id']}", headers=ORG_DEMO_HEADERS
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/samples/{sample['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/datasets/{dataset['id']}", headers=ORG_DEMO_HEADERS
        ).status_code
        == 404
    )
    remaining = client.get(
        f"/api/v1/experiments/{experiment['id']}/samples", headers=ORG_DEMO_HEADERS
    ).json()
    assert remaining == []


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_cross_tenant_sample_delete_is_blocked(client: TestClient) -> None:
    experiment = client.post(
        "/api/v1/experiments",
        headers=ADMIN_HEADERS,
        json={"organization_id": "org_qc", "name": "QC plate", "blocks": []},
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=ADMIN_HEADERS,
        json={
            "organization_id": "org_qc",
            "experiment_id": experiment["id"],
            "name": "QC1",
            "sample_type": "dna",
        },
    ).json()

    forbidden = client.delete(
        f"/api/v1/samples/{sample['id']}", headers=ORG_DEMO_HEADERS
    )
    assert forbidden.status_code == 403
    assert (
        client.get(
            f"/api/v1/samples/{sample['id']}", headers=ADMIN_HEADERS
        ).status_code
        == 200
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_sample_well_move_and_duplicate_still_blocked(client: TestClient) -> None:
    experiment_id = _create_experiment(client)["id"]
    first = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment_id,
            "name": "s1",
            "well_position": "A1",
        },
    ).json()
    second = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment_id,
            "name": "s2",
            "well_position": "A2",
        },
    ).json()

    moved = client.patch(
        f"/api/v1/samples/{first['id']}",
        headers=ORG_DEMO_HEADERS,
        json={"well_position": "B3"},
    )
    assert moved.status_code == 200
    assert moved.json()["well_position"] == "B3"

    clash = client.patch(
        f"/api/v1/samples/{first['id']}",
        headers=ORG_DEMO_HEADERS,
        json={"well_position": "A2"},
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "well_occupied"
    assert second["well_position"] == "A2"


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_full_hierarchy_create_and_read(client: TestClient) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "name": "My Lab",
            "category": "molecular_biology",
        },
    ).json()

    project = client.post(
        "/api/v1/projects",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "workspace_id": workspace["id"],
            "name": "Reporter cloning",
        },
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    experiment = _create_experiment(client, project_id=project_id)
    experiment_id = experiment["id"]
    assert experiment["project_id"] == project_id

    sample = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment_id,
            "name": "Colony 1",
            "sample_type": "dna",
            "well_position": "A1",
        },
    )
    assert sample.status_code == 201
    sample_id = sample.json()["id"]
    assert sample.json()["well_position"] == "A1"

    dataset = client.post(
        "/api/v1/datasets",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "sample_id": sample_id,
            "name": "Sanger read",
            "dataset_type": "dna_sequence",
            "content": {"sequence": "ATGC"},
        },
    )
    assert dataset.status_code == 201

    # Read back down the tree.
    assert (
        client.get(
            f"/api/v1/experiments/{experiment_id}/samples", headers=ORG_DEMO_HEADERS
        ).json()[0]["id"]
        == sample_id
    )
    assert (
        client.get(
            f"/api/v1/samples/{sample_id}/datasets", headers=ORG_DEMO_HEADERS
        ).json()[0]["name"]
        == "Sanger read"
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_experiment_versioning_advances_head(client: TestClient) -> None:
    experiment = _create_experiment(client)
    experiment_id = experiment["id"]
    v1 = experiment["head_version_id"]

    commit = client.post(
        f"/api/v1/experiments/{experiment_id}/versions",
        headers=ORG_DEMO_HEADERS,
        json={
            "message": "Add gel image",
            "blocks": [{"type": "text", "content": "band at 500bp"}],
        },
    )
    assert commit.status_code == 201
    v2 = commit.json()
    assert v2["version_number"] == 2
    assert v2["parent_version_id"] == v1

    refreshed = client.get(
        f"/api/v1/experiments/{experiment_id}", headers=ORG_DEMO_HEADERS
    ).json()
    assert refreshed["head_version_id"] == v2["id"]
    assert refreshed["version_count"] == 2

    history = client.get(
        f"/api/v1/experiments/{experiment_id}/versions", headers=ORG_DEMO_HEADERS
    ).json()
    assert [v["version_number"] for v in history] == [1, 2]


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_signed_version_is_immutable(client: TestClient) -> None:
    experiment = _create_experiment(client)
    experiment_id = experiment["id"]
    version_id = experiment["head_version_id"]

    def patch(status: str):
        return client.patch(
            f"/api/v1/experiments/{experiment_id}/versions/{version_id}",
            headers=ORG_DEMO_HEADERS,
            json={"status": status},
        )

    assert patch("in_review").status_code == 200
    assert patch("signed").status_code == 200
    locked = patch("in_review")
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "version_locked"


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_sample_rejects_invalid_and_duplicate_wells(client: TestClient) -> None:
    experiment_id = _create_experiment(client)["id"]

    bad = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment_id,
            "name": "bad",
            "well_position": "Z99",
        },
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_well"

    first = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment_id,
            "name": "s1",
            "well_position": "b2",
        },
    )
    assert first.status_code == 201
    assert first.json()["well_position"] == "B2"

    dup = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment_id,
            "name": "s2",
            "well_position": "B2",
        },
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "well_occupied"


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_experiment_enforces_96_sample_limit(client: TestClient) -> None:
    experiment_id = _create_experiment(client)["id"]
    for index in range(96):
        response = client.post(
            "/api/v1/samples",
            headers=ORG_DEMO_HEADERS,
            json={
                "organization_id": "org_demo",
                "experiment_id": experiment_id,
                "name": f"s{index}",
            },
        )
        assert response.status_code == 201, response.text

    overflow = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment_id,
            "name": "one too many",
        },
    )
    assert overflow.status_code == 409
    assert overflow.json()["error"]["code"] == "plate_full"


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_cross_tenant_reads_are_blocked(client: TestClient) -> None:
    # Admin can write into org_qc; a demo-only actor must not see it.
    qc_experiment = client.post(
        "/api/v1/experiments",
        headers=ADMIN_HEADERS,
        json={"organization_id": "org_qc", "name": "QC only", "blocks": []},
    ).json()

    forbidden = client.get(
        f"/api/v1/experiments/{qc_experiment['id']}", headers=ORG_DEMO_HEADERS
    )
    assert forbidden.status_code == 403

    scoped = client.get("/api/v1/experiments", headers=ORG_DEMO_HEADERS)
    assert all(item["organization_id"] == "org_demo" for item in scoped.json())


# --------------------------------------------------------------------------- #
# Regressions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_update_rejects_explicit_null_on_required_fields(client: TestClient) -> None:
    """Update payloads type every field Optional, but only some are nullable.

    An explicit JSON null used to flow through model_copy() unvalidated: the
    memory store persisted a project with name=None, and SQLite raised a NOT
    NULL IntegrityError (500).
    """
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "WS", "category": "genomics"},
    ).json()
    project = client.post(
        "/api/v1/projects",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "workspace_id": workspace["id"],
            "name": "Keep me",
        },
    ).json()

    nulled = client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=ORG_DEMO_HEADERS,
        json={"name": None},
    )
    assert nulled.status_code == 422
    assert nulled.json()["error"]["code"] == "invalid_update"

    unchanged = client.get(
        f"/api/v1/projects/{project['id']}", headers=ORG_DEMO_HEADERS
    )
    assert unchanged.json()["name"] == "Keep me"

    experiment = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "E", "blocks": []},
    ).json()
    sample = client.post(
        "/api/v1/samples",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "experiment_id": experiment["id"],
            "name": "S1",
            "sample_type": "dna",
        },
    ).json()

    assert (
        client.patch(
            f"/api/v1/samples/{sample['id']}",
            headers=ORG_DEMO_HEADERS,
            json={"status": None},
        ).status_code
        == 422
    )
    # well_position is genuinely nullable — clearing it must still work.
    assert (
        client.patch(
            f"/api/v1/samples/{sample['id']}",
            headers=ORG_DEMO_HEADERS,
            json={"well_position": None},
        ).status_code
        == 200
    )


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_concurrent_commits_allocate_unique_version_numbers(client: TestClient) -> None:
    """Version numbers used to be allocated read-modify-write across two
    transactions: SQLite returned 500 for the losers, and the memory store
    silently persisted duplicate version_numbers with a desynced version_count.
    """
    import threading

    experiment = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Racy", "blocks": []},
    ).json()

    commits = 8
    codes: list[int] = []

    def commit(index: int) -> None:
        response = client.post(
            f"/api/v1/experiments/{experiment['id']}/versions",
            headers=ORG_DEMO_HEADERS,
            json={"message": f"commit {index}", "blocks": []},
        )
        codes.append(response.status_code)

    threads = [threading.Thread(target=commit, args=(i,)) for i in range(commits)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert codes == [201] * commits

    versions = client.get(
        f"/api/v1/experiments/{experiment['id']}/versions", headers=ORG_DEMO_HEADERS
    ).json()
    numbers = sorted(version["version_number"] for version in versions)
    # v1 from create_experiment, plus one per concurrent commit, no duplicates.
    assert numbers == list(range(1, commits + 2))

    head = client.get(
        f"/api/v1/experiments/{experiment['id']}", headers=ORG_DEMO_HEADERS
    ).json()
    assert head["version_count"] == len(versions)
    assert head["head_version_id"] in {version["id"] for version in versions}


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_created_experiment_always_has_its_first_version(client: TestClient) -> None:
    """create_experiment writes the experiment and its v1 in one transaction, so
    HEAD can never dangle."""
    experiment = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Atomic", "blocks": []},
    ).json()

    assert experiment["version_count"] == 1
    assert experiment["head_version_id"] is not None

    versions = client.get(
        f"/api/v1/experiments/{experiment['id']}/versions", headers=ORG_DEMO_HEADERS
    ).json()
    assert [version["id"] for version in versions] == [experiment["head_version_id"]]


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_concurrent_creates_cannot_overfill_the_plate(client: TestClient) -> None:
    """The cap and well uniqueness used to be checked before the insert, in a
    separate transaction, so concurrent creates could both pass the check — a
    97th sample landed on a 96-well plate.
    """
    import threading

    experiment = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Plate", "blocks": []},
    ).json()

    for index in range(95):
        client.post(
            "/api/v1/samples",
            headers=ORG_DEMO_HEADERS,
            json={
                "organization_id": "org_demo",
                "experiment_id": experiment["id"],
                "name": f"seed {index}",
                "sample_type": "dna",
            },
        )

    codes: list[int] = []

    def add(index: int) -> None:
        response = client.post(
            "/api/v1/samples",
            headers=ORG_DEMO_HEADERS,
            json={
                "organization_id": "org_demo",
                "experiment_id": experiment["id"],
                "name": f"race {index}",
                "sample_type": "dna",
            },
        )
        codes.append(response.status_code)

    threads = [threading.Thread(target=add, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Exactly one of the ten racers takes the last well; the rest are refused.
    assert codes.count(201) == 1
    assert codes.count(409) == 9

    samples = client.get(
        f"/api/v1/experiments/{experiment['id']}/samples", headers=ORG_DEMO_HEADERS
    ).json()
    assert len(samples) == 96


@pytest.mark.parametrize("client", CLIENT_FIXTURES, indirect=True)
def test_concurrent_creates_cannot_double_book_a_well(client: TestClient) -> None:
    import threading

    experiment = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo", "name": "Wells", "blocks": []},
    ).json()

    codes: list[int] = []

    def claim(index: int) -> None:
        response = client.post(
            "/api/v1/samples",
            headers=ORG_DEMO_HEADERS,
            json={
                "organization_id": "org_demo",
                "experiment_id": experiment["id"],
                "name": f"claim {index}",
                "sample_type": "dna",
                "well_position": "B2",
            },
        )
        codes.append(response.status_code)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert codes.count(201) == 1
    assert codes.count(409) == 9

    samples = client.get(
        f"/api/v1/experiments/{experiment['id']}/samples", headers=ORG_DEMO_HEADERS
    ).json()
    assert [s["well_position"] for s in samples] == ["B2"]
