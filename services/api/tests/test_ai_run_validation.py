"""Agent run requests are validated before the SSE stream starts."""

HEADERS = {"Authorization": "Bearer org-demo-token"}


def _run(client, session_id, headers=HEADERS):
    return client.post(
        "/api/v1/ai/runs",
        headers=headers,
        json={"session_id": session_id, "message": "hi", "context": {}},
    )


def test_run_with_missing_session_returns_404(memory_client) -> None:
    response = _run(memory_client, "does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_run_against_other_tenant_session_is_rejected(memory_client) -> None:
    admin = {"Authorization": "Bearer demo-admin-token"}
    created = memory_client.post(
        "/api/v1/ai/sessions", headers=admin, json={"organization_id": "org_qc"}
    )
    session_id = created.json()["id"]
    response = _run(memory_client, session_id, HEADERS)
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")
