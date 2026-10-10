"""Structured logging and request correlation."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from helixos.main import create_app
from helixos.observability import ContextFilter, JsonFormatter

ORG_DEMO = {"Authorization": "Bearer org-demo-token"}


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.addFilter(ContextFilter())
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def logs():
    handler = Capture()
    logger = logging.getLogger("helixos")
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)


def _access(records):
    return [r for r in records if r.name == "helixos.access" and r.getMessage() == "request"]


def test_response_carries_generated_request_id(memory_client) -> None:
    response = memory_client.get("/api/v1/workspaces", headers=ORG_DEMO)
    assert response.headers["X-Request-ID"].startswith("req_")


def test_valid_inbound_request_id_is_echoed_and_invalid_replaced(memory_client) -> None:
    ok = memory_client.get("/health", headers={"X-Request-ID": "trace-abc.123"})
    assert ok.headers["X-Request-ID"] == "trace-abc.123"
    bad = memory_client.get("/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert bad.headers["X-Request-ID"].startswith("req_")


def test_error_envelope_includes_request_id(memory_client) -> None:
    response = memory_client.get("/api/v1/workspaces")  # no token
    assert response.status_code == 401
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_access_log_has_context_and_omits_query_string(memory_client, logs) -> None:
    response = memory_client.get(
        "/api/v1/workspaces?organization_id=org_demo&secret=hunter2", headers=ORG_DEMO
    )
    record = _access(logs)[-1]
    assert record.request_id == response.headers["X-Request-ID"]
    assert record.actor == "user_demo_scientist"
    assert (record.method, record.path, record.status) == ("GET", "/api/v1/workspaces", 200)
    assert record.duration_ms >= 0
    assert "hunter2" not in JsonFormatter().format(record)


def test_unhandled_exception_returns_enveloped_500_and_is_logged(logs) -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaput")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "internal_error" and "kaput" not in json.dumps(body)
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert any(r.exc_info for r in logs if r.name == "helixos.access")
    assert _access(logs)[-1].status == 500


def test_request_id_reaches_logs_emitted_in_threadpool(logs) -> None:
    app = create_app()

    @app.get("/work")
    def work() -> dict[str, str]:  # sync endpoint -> runs in a worker thread
        logging.getLogger("helixos.test").info("doing work")
        return {}

    response = TestClient(app).get("/work")
    record = next(r for r in logs if r.getMessage() == "doing work")
    assert record.request_id == response.headers["X-Request-ID"]


def test_json_formatter_emits_one_valid_object_with_extras() -> None:
    record = logging.LogRecord("helixos.x", logging.WARNING, __file__, 1, "hello %s", ("w",), None)
    record.job_id = "job_1"
    line = JsonFormatter().format(record)
    parsed = json.loads(line)
    assert parsed["message"] == "hello w" and parsed["level"] == "warning"
    assert parsed["job_id"] == "job_1" and "\n" not in line


def test_agent_run_logs_carry_run_id(memory_client, logs) -> None:
    session_id = memory_client.post(
        "/api/v1/ai/sessions", headers=ORG_DEMO, json={"organization_id": "org_demo"}
    ).json()["id"]
    memory_client.post(
        "/api/v1/ai/runs",
        headers=ORG_DEMO,
        json={"session_id": session_id, "message": "hi", "context": {}},
    )
    completed = next(r for r in logs if r.getMessage() == "agent run completed")
    assert completed.run_id.startswith("run_") and completed.actor == "user_demo_scientist"


def test_failed_agent_run_error_frame_carries_request_id(memory_client, monkeypatch) -> None:
    from helixos.ai import service as ai_service

    class Exploding:
        name = "exploding"

        async def stream_response(self, _context):
            raise RuntimeError("provider down")
            yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(ai_service, "get_agent_provider", lambda: Exploding())
    session_id = memory_client.post(
        "/api/v1/ai/sessions", headers=ORG_DEMO, json={"organization_id": "org_demo"}
    ).json()["id"]
    response = memory_client.post(
        "/api/v1/ai/runs",
        headers=ORG_DEMO,
        json={"session_id": session_id, "message": "hi", "context": {}},
    )
    frame = next(
        json.loads(line[len("data: ") :])
        for block in response.text.split("\n\n")
        if block.startswith("event: error")
        for line in block.splitlines()
        if line.startswith("data: ")
    )
    assert frame["request_id"] == response.headers["X-Request-ID"]
