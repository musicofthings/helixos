"""Audit event API tests."""

from fastapi.testclient import TestClient

from helixos.main import create_app

ORG_DEMO_HEADERS = {"Authorization": "Bearer org-demo-token"}


def test_agent_run_records_audit_events() -> None:
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
            "context": {},
        },
    ) as response:
        assert response.status_code == 200
        response.read()

    audit_response = client.get(
        "/api/v1/audit/events",
        headers=ORG_DEMO_HEADERS,
        params={"organization_id": "org_demo"},
    )
    assert audit_response.status_code == 200
    event_types = {event["event_type"] for event in audit_response.json()}
    assert "ai.session_created" in event_types
    assert "ai.run_started" in event_types
    assert "ai.tool_call" in event_types
    assert "ai.run_completed" in event_types


def test_audit_events_are_scoped_to_actor_organizations() -> None:
    client = TestClient(create_app())
    response = client.get(
        "/api/v1/audit/events",
        headers=ORG_DEMO_HEADERS,
        params={"organization_id": "org_qc"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
