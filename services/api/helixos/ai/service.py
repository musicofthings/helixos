"""Agent runtime and provider abstraction."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

from helixos.ai.models import AgentRunRecord, AgentRunStatus, AgentSessionRecord
from helixos.ai.providers import AgentPromptContext, get_agent_provider
from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.eln.service import experiment_service
from helixos.errors import api_error

PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / "eln_copilot.md"


class AgentService:
    """Coordinates agent sessions and streaming runs."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSessionRecord] = {}
        self._runs: dict[str, AgentRunRecord] = {}

    def create_session(self, organization_id: str, actor: Actor) -> AgentSessionRecord:
        """Create an agent session scoped to a tenant."""
        organization_service.require_access(actor, organization_id)
        session = AgentSessionRecord.create(organization_id)
        self._sessions[session.id] = session
        audit_service.record(
            organization_id=organization_id,
            actor=actor,
            event_type="ai.session_created",
            resource_type="agent_session",
            resource_id=session.id,
            payload={"organization_id": organization_id},
        )
        return session

    def get_session(self, session_id: str) -> AgentSessionRecord:
        """Return a session or raise when missing."""
        session = self._sessions.get(session_id)
        if session is None:
            raise api_error(status_code=404, code="not_found", message="Agent session not found")
        return session

    async def stream_run(
        self,
        session_id: str,
        message: str,
        actor: Actor,
        *,
        experiment_id: str | None = None,
        experiment_title: str | None = None,
        sequence_length: int | None = None,
    ) -> AsyncIterator[str]:
        """Execute an agent run and yield SSE frames."""
        session = self.get_session(session_id)
        organization_service.require_access(actor, session.organization_id)

        run = AgentRunRecord.create(session_id, message)
        self._runs[run.id] = run
        run.status = AgentRunStatus.RUNNING
        audit_service.record(
            organization_id=session.organization_id,
            actor=actor,
            event_type="ai.run_started",
            resource_type="agent_run",
            resource_id=run.id,
            payload={
                "session_id": session_id,
                "message": message,
                "experiment_id": experiment_id,
                "experiment_title": experiment_title,
                "sequence_length": sequence_length,
            },
        )

        try:
            async for frame in self._execute_run(
                run=run,
                actor=actor,
                organization_id=session.organization_id,
                experiment_id=experiment_id,
                experiment_title=experiment_title,
                sequence_length=sequence_length,
            ):
                yield frame
            run.status = AgentRunStatus.COMPLETED
            run.completed_at = run.created_at
            audit_service.record(
                organization_id=session.organization_id,
                actor=actor,
                event_type="ai.run_completed",
                resource_type="agent_run",
                resource_id=run.id,
                payload={"session_id": session_id, "event_count": len(run.events)},
            )
        except Exception as exc:  # noqa: BLE001 - surface agent failures as SSE errors
            run.status = AgentRunStatus.FAILED
            run.error = str(exc)
            audit_service.record(
                organization_id=session.organization_id,
                actor=actor,
                event_type="ai.run_failed",
                resource_type="agent_run",
                resource_id=run.id,
                payload={"session_id": session_id, "error": str(exc)},
            )
            yield self._sse("error", {"message": str(exc), "run_id": run.id})
            yield self._sse("done", {"run_id": run.id, "status": run.status})

    async def _execute_run(
        self,
        *,
        run: AgentRunRecord,
        actor: Actor,
        organization_id: str,
        experiment_id: str | None,
        experiment_title: str | None,
        sequence_length: int | None,
    ) -> AsyncIterator[str]:
        experiments = experiment_service.list_experiments(actor)
        visible = [item for item in experiments if item.organization_id == organization_id]

        tool_payload = {
            "tool": "list_experiments",
            "status": "completed",
            "count": len(visible),
        }
        run.events.append({"event": "tool_call", "data": tool_payload})
        self._record_tool_call(
            organization_id=organization_id,
            actor=actor,
            run_id=run.id,
            tool_payload=tool_payload,
        )
        yield self._sse("tool_call", tool_payload)

        provider = get_agent_provider()
        provider_payload = {"tool": "provider", "status": "running", "name": provider.name}
        run.events.append({"event": "tool_call", "data": provider_payload})
        self._record_tool_call(
            organization_id=organization_id,
            actor=actor,
            run_id=run.id,
            tool_payload=provider_payload,
        )
        yield self._sse("tool_call", provider_payload)

        prompt_context = AgentPromptContext(
            system_prompt=self._load_system_prompt(),
            user_message=run.message,
            experiment_count=len(visible),
            experiment_title=experiment_title,
            experiment_id=experiment_id,
            sequence_length=sequence_length,
            tool_summaries=[f"{len(visible)} visible experiment record(s)"],
        )

        async for token in provider.stream_response(prompt_context):
            token_payload = {"content": token, "run_id": run.id}
            run.events.append({"event": "token", "data": token_payload})
            yield self._sse("token", token_payload)

        done_payload = {"run_id": run.id, "status": AgentRunStatus.COMPLETED, "provider": provider.name}
        run.events.append({"event": "done", "data": done_payload})
        yield self._sse("done", done_payload)

    def _record_tool_call(
        self,
        *,
        organization_id: str,
        actor: Actor,
        run_id: str,
        tool_payload: dict[str, object],
    ) -> None:
        audit_service.record(
            organization_id=organization_id,
            actor=actor,
            event_type="ai.tool_call",
            resource_type="agent_run",
            resource_id=run_id,
            payload=tool_payload,
        )

    def _load_system_prompt(self) -> str:
        if PROMPT_PATH.exists():
            return PROMPT_PATH.read_text(encoding="utf-8")
        return "You are HelixOS ELN Copilot."

    @staticmethod
    def _sse(event: str, data: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"


agent_service = AgentService()
