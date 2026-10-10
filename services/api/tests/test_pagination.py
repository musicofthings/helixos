"""List endpoints are bounded and describe pages in headers."""

import pytest
from fastapi.testclient import TestClient

from backends import ELN_CLIENT_FIXTURES

ORG_DEMO = {"Authorization": "Bearer org-demo-token"}


@pytest.fixture
def client(request) -> TestClient:
    return request.getfixturevalue(request.param)


def _seed_projects(client: TestClient, count: int) -> str:
    workspace = client.post(
        "/api/v1/workspaces",
        headers=ORG_DEMO,
        json={"organization_id": "org_demo", "name": "Paged", "category": "custom"},
    ).json()
    for i in range(count):
        response = client.post(
            "/api/v1/projects",
            headers=ORG_DEMO,
            json={
                "organization_id": "org_demo",
                "workspace_id": workspace["id"],
                "name": f"p{i:02d}",
            },
        )
        assert response.status_code == 201, response.text
    return workspace["id"]


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_pages_cover_every_item_once_in_order(client) -> None:
    workspace_id = _seed_projects(client, 7)
    url = f"/api/v1/projects?workspace_id={workspace_id}"

    seen: list[str] = []
    offset: str | None = "0"
    pages = 0
    while offset is not None:
        response = client.get(f"{url}&limit=3&offset={offset}", headers=ORG_DEMO)
        assert response.status_code == 200
        assert response.headers["X-Total-Count"] == "7"
        seen += [p["name"] for p in response.json()]
        offset = response.headers.get("X-Next-Offset")
        pages += 1

    assert pages == 3
    assert seen == [f"p{i:02d}" for i in range(7)]


@pytest.mark.parametrize("client", ELN_CLIENT_FIXTURES, indirect=True)
def test_last_page_has_no_next_offset_and_past_end_is_empty(client) -> None:
    workspace_id = _seed_projects(client, 2)
    url = f"/api/v1/projects?workspace_id={workspace_id}"

    full = client.get(f"{url}&limit=2", headers=ORG_DEMO)
    assert "X-Next-Offset" not in full.headers
    beyond = client.get(f"{url}&offset=50", headers=ORG_DEMO)
    assert beyond.json() == []
    assert beyond.headers["X-Total-Count"] == "2"


def test_invalid_page_parameters_are_rejected(memory_client) -> None:
    for query in ("limit=0", "limit=501", "offset=-1"):
        response = memory_client.get(f"/api/v1/projects?{query}", headers=ORG_DEMO)
        assert response.status_code == 422, query


def test_default_page_size_bounds_responses(memory_client) -> None:
    workspace_id = _seed_projects(memory_client, 3)
    response = memory_client.get(
        f"/api/v1/projects?workspace_id={workspace_id}", headers=ORG_DEMO
    )
    assert len(response.json()) == 3
    assert response.headers["X-Total-Count"] == "3"


def test_cors_exposes_pagination_headers(memory_client) -> None:
    response = memory_client.get(
        "/api/v1/workspaces",
        headers={**ORG_DEMO, "Origin": "http://localhost:3000"},
    )
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "X-Total-Count" in exposed and "X-Next-Offset" in exposed
