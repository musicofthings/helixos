"""Pagination is applied in the database query, and shared-access visibility
is preserved when listing."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from backends import ELN_CLIENT_FIXTURES
from helixos.db.session import get_engine
from helixos.eln import sql_store
from helixos.eln.orm import ProjectORM
from helixos.eln.service import eln_service
from helixos.eln.stores import PageRequest

ORG_DEMO = {"Authorization": "Bearer org-demo-token"}
ADMIN = {"Authorization": "Bearer demo-admin-token"}


@pytest.fixture
def client(request) -> TestClient:
    return request.getfixturevalue(request.param)


def _workspace(client, headers, org, name="W") -> dict:
    response = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"organization_id": org, "name": name, "category": "custom"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _project(client, headers, org, workspace_id, name) -> dict:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"organization_id": org, "workspace_id": workspace_id, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _experiment(client, headers, org, project_id, name) -> dict:
    response = client.post(
        "/api/v1/experiments",
        headers=headers,
        json={"organization_id": org, "project_id": project_id, "name": name, "blocks": []},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_sql_store_applies_limit_and_offset_in_the_query(sqlite_client, monkeypatch) -> None:
    workspace = _workspace(sqlite_client, ORG_DEMO, "org_demo")
    for i in range(12):
        _project(sqlite_client, ORG_DEMO, "org_demo", workspace["id"], f"p{i:02d}")

    statements: list[str] = []
    event.listen(
        get_engine(), "before_cursor_execute",
        lambda _c, _cur, statement, *_a: statements.append(statement),
    )
    converted = 0
    original = sql_store._to_project

    def counting(row):
        nonlocal converted
        converted += 1
        return original(row)

    monkeypatch.setattr(sql_store, "_to_project", counting)

    result = eln_service._store.page_projects(
        ["org_demo"], workspace_id=workspace["id"], page=PageRequest(limit=5, offset=10)
    )

    assert result.total == 12
    assert [p.name for p in result.items] == ["p10", "p11"]
    assert converted == 2, "rows beyond the page must not be loaded"
    select = next(s for s in statements if f"FROM {ProjectORM.__tablename__}" in s and "count(" not in s.lower())
    assert "LIMIT" in select and "OFFSET" in select
    assert any("count(" in s.lower() for s in statements), "total comes from a COUNT query"


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_paging_is_stable_and_complete_for_every_entity(client) -> None:
    workspace = _workspace(client, ORG_DEMO, "org_demo")
    project = _project(client, ORG_DEMO, "org_demo", workspace["id"], "P")
    experiments = [
        _experiment(client, ORG_DEMO, "org_demo", project["id"], f"e{i}") for i in range(5)
    ]
    for i in range(4):
        client.post(
            f"/api/v1/experiments/{experiments[0]['id']}/versions",
            headers=ORG_DEMO,
            json={"message": f"v{i + 2}", "blocks": []},
        )
    for i in range(5):
        client.post(
            "/api/v1/samples",
            headers=ORG_DEMO,
            json={"organization_id": "org_demo", "experiment_id": experiments[0]["id"],
                  "name": f"s{i}", "sample_type": "dna"},
        )

    def walk(url: str) -> list[dict]:
        out, offset = [], 0
        while True:
            response = client.get(f"{url}{'&' if '?' in url else '?'}limit=2&offset={offset}", headers=ORG_DEMO)
            assert response.status_code == 200, response.text
            out += response.json()
            if "X-Next-Offset" not in response.headers:
                assert int(response.headers["X-Total-Count"]) == len(out)
                return out
            offset = int(response.headers["X-Next-Offset"])

    assert [e["name"] for e in walk(f"/api/v1/experiments?project_id={project['id']}")] == [
        f"e{i}" for i in range(5)
    ]
    assert [v["version_number"] for v in walk(f"/api/v1/experiments/{experiments[0]['id']}/versions")] == [1, 2, 3, 4, 5]
    assert [s["name"] for s in walk(f"/api/v1/experiments/{experiments[0]['id']}/samples")] == [
        f"s{i}" for i in range(5)
    ]


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_share_grantee_pages_only_shared_workspaces(client) -> None:
    shared_ws = _workspace(client, ADMIN, "org_qc", "Shared")
    private_ws = _workspace(client, ADMIN, "org_qc", "Private")
    shared_project = _project(client, ADMIN, "org_qc", shared_ws["id"], "visible")
    for i in range(3):
        _project(client, ADMIN, "org_qc", shared_ws["id"], f"visible{i}")
    private_project = _project(client, ADMIN, "org_qc", private_ws["id"], "hidden")
    _experiment(client, ADMIN, "org_qc", shared_project["id"], "shared-exp")
    _experiment(client, ADMIN, "org_qc", private_project["id"], "hidden-exp")

    token = client.post(
        f"/api/v1/workspaces/{shared_ws['id']}/invites", headers=ADMIN,
        json={"role": "viewer", "expires_in_hours": 1},
    ).json()["token"]
    assert client.post(f"/api/v1/workspace-invites/{token}/accept", headers=ORG_DEMO).status_code == 201

    # org-demo user is not a member of org_qc: only the shared workspace is visible.
    projects = client.get("/api/v1/projects?organization_id=org_qc&limit=2", headers=ORG_DEMO)
    assert projects.status_code == 200
    assert projects.headers["X-Total-Count"] == "4"
    assert len(projects.json()) == 2 and projects.headers["X-Next-Offset"] == "2"
    assert all(p["workspace_id"] == shared_ws["id"] for p in projects.json())

    experiments = client.get("/api/v1/experiments?organization_id=org_qc", headers=ORG_DEMO).json()
    assert [e["name"] for e in experiments] == ["shared-exp"]

    workspaces = client.get("/api/v1/workspaces?organization_id=org_qc", headers=ORG_DEMO).json()
    assert [w["id"] for w in workspaces] == [shared_ws["id"]]

    # Without an org filter the grantee sees their own org plus the shared workspace.
    everything = client.get("/api/v1/workspaces", headers=ORG_DEMO).json()
    assert shared_ws["id"] in {w["id"] for w in everything}
    assert private_ws["id"] not in {w["id"] for w in everything}


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_listing_an_org_you_have_no_access_to_is_forbidden(client) -> None:
    for path in ("projects", "protocols", "experiments", "workspaces"):
        response = client.get(f"/api/v1/{path}?organization_id=org_qc", headers=ORG_DEMO)
        assert response.status_code == 403, path


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_grantee_of_an_empty_shared_workspace_gets_an_empty_page(client) -> None:
    workspace = _workspace(client, ADMIN, "org_qc", "Empty")
    token = client.post(
        f"/api/v1/workspaces/{workspace['id']}/invites", headers=ADMIN,
        json={"role": "viewer", "expires_in_hours": 1},
    ).json()["token"]
    client.post(f"/api/v1/workspace-invites/{token}/accept", headers=ORG_DEMO)

    response = client.get("/api/v1/projects?organization_id=org_qc", headers=ORG_DEMO)
    assert response.status_code == 200
    assert response.json() == [] and response.headers["X-Total-Count"] == "0"
