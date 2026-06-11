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


def test_create_agent_session() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/ai/sessions",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_demo"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("sess_")
    assert body["organization_id"] == "org_demo"


def test_agent_run_streams_sse_events() -> None:
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
        json={
            "session_id": session_id,
            "message": "Summarize experiments",
            "context": {"sequence_length": 96},
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode("utf-8")

    assert "event: tool_call" in body
    assert "event: token" in body
    assert "event: done" in body


def test_agent_session_rejects_cross_tenant_access() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/ai/sessions",
        headers=ORG_DEMO_HEADERS,
        json={"organization_id": "org_qc"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_mcp_job_requires_bridge() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/mcp/jobs",
        headers=ORG_DEMO_HEADERS,
        json={
            "connector_id": "biopython-local",
            "tool": "analyze_sequence",
            "arguments": {"sequence": "ATGC"},
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "bridge_unavailable"


def test_mcp_job_rejects_unknown_connector() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/mcp/jobs",
        headers=ORG_DEMO_HEADERS,
        json={
            "connector_id": "unknown",
            "tool": "analyze_sequence",
            "arguments": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_update_experiment_status() -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "title": "Status transition test",
            "blocks": [{"type": "text", "content": "Draft note."}],
        },
    )
    experiment_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/experiments/{experiment_id}",
        headers=ORG_DEMO_HEADERS,
        json={"status": "in_review"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_review"


def test_update_experiment_status_rejects_invalid_transition() -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "title": "Invalid transition test",
            "blocks": [],
        },
    )
    experiment_id = create_response.json()["id"]

    response = client.patch(
        f"/api/v1/experiments/{experiment_id}",
        headers=ORG_DEMO_HEADERS,
        json={"status": "signed"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_transition"


def test_experiment_create_records_audit_event() -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/api/v1/experiments",
        headers=ORG_DEMO_HEADERS,
        json={
            "organization_id": "org_demo",
            "title": "Audit test experiment",
            "blocks": [],
        },
    )
    experiment_id = create_response.json()["id"]

    audit_response = client.get(
        "/api/v1/audit/events?organization_id=org_demo",
        headers=ORG_DEMO_HEADERS,
    )

    assert audit_response.status_code == 200
    events = audit_response.json()
    assert any(
        event["event_type"] == "eln.experiment_created" and event["resource_id"] == experiment_id for event in events
    )
