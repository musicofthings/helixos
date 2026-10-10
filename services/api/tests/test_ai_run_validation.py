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


def _admin_actor():
    from helixos.auth.service import DEMO_TOKENS

    return DEMO_TOKENS["org-demo-token"]


def test_done_frame_follows_completion_audit(memory_client) -> None:
    from helixos.audit.service import audit_service

    session_id = memory_client.post(
        "/api/v1/ai/sessions", headers=HEADERS, json={"organization_id": "org_demo"}
    ).json()["id"]
    with memory_client.stream(
        "POST",
        "/api/v1/ai/runs",
        headers=HEADERS,
        json={"session_id": session_id, "message": "hi", "context": {}},
    ) as response:
        body = "".join(response.iter_text())
    assert "event: done" in body
    events = audit_service.list_for_actor(_admin_actor(), "org_demo", limit=200)
    assert any(e.event_type == "ai.run_completed" for e in events)


def test_disconnect_marks_run_cancelled() -> None:
    import asyncio

    from helixos.ai.models import AgentRunStatus
    from helixos.ai.service import AgentService

    service = AgentService()
    actor = _admin_actor()
    session = service.create_session("org_demo", actor)

    async def scenario():
        stream = service.stream_run(session.id, "hi", actor)
        await stream.__anext__()
        await stream.aclose()

    asyncio.run(scenario())
    run = next(iter(service._runs.values()))
    assert run.status == AgentRunStatus.CANCELLED


def test_session_and_run_retention_is_bounded(monkeypatch) -> None:
    from helixos.ai import service as ai_service

    monkeypatch.setattr(ai_service, "MAX_RETAINED_SESSIONS", 3)
    svc = ai_service.AgentService()
    actor = _admin_actor()
    ids = [svc.create_session("org_demo", actor).id for _ in range(5)]
    assert len(svc._sessions) == 3
    assert ids[0] not in svc._sessions and ids[-1] in svc._sessions
