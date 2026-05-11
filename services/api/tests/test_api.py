"""API smoke tests for the HelixOS starter kit."""

from fastapi.testclient import TestClient

from helixos.main import create_app

AUTH_HEADERS = {"Authorization": "Bearer demo-admin-token"}
ORG_DEMO_HEADERS = {"Authorization": "Bearer org-demo-token"}


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_modules_include_phase_one() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/modules", headers=AUTH_HEADERS)
    assert response.status_code == 200
    module_ids = {module["id"] for module in response.json()}
    assert {"auth", "eln", "molecular", "inventory", "ai", "mcp"}.issubset(module_ids)


def test_create_experiment_draft() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/experiments",
        headers=AUTH_HEADERS,
        json={
            "organization_id": "org_demo",
            "title": "Gibson assembly",
            "blocks": [{"type": "text", "content": "Draft assembly plan."}],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("exp_")
    assert body["status"] == "draft"
    assert body["organization_id"] == "org_demo"


def test_experiment_listing_is_scoped_to_actor_organizations() -> None:
    client = TestClient(create_app())
    client.post(
        "/api/v1/experiments",
        headers=AUTH_HEADERS,
        json={"organization_id": "org_demo", "title": "Demo experiment", "blocks": []},
    )
    client.post(
        "/api/v1/experiments",
        headers=AUTH_HEADERS,
        json={"organization_id": "org_qc", "title": "QC experiment", "blocks": []},
    )

    response = client.get("/api/v1/experiments", headers=ORG_DEMO_HEADERS)

    assert response.status_code == 200
    assert {item["organization_id"] for item in response.json()} == {"org_demo"}


def test_experiment_create_rejects_unavailable_organization() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_qc", "title": "Cross-tenant write", "blocks": []},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_protected_routes_require_bearer_token() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/experiments")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_list_organizations_visible_to_actor() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/organizations", headers=ORG_DEMO_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert [organization["id"] for organization in body] == ["org_demo"]


def test_get_sequence_metadata() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/sequences/seq_demo_reporter", headers=ORG_DEMO_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "seq_demo_reporter"
    assert body["organization_id"] == "org_demo"
    assert body["molecule_type"] == "dna"


def test_sequence_access_is_tenant_scoped() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/sequences/seq_qc_amplicon", headers=ORG_DEMO_HEADERS)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
