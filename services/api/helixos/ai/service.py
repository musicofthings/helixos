"""Agent runtime and provider abstraction."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from helixos import limits, ratelimit
from helixos.ai.budget import Reservation, budget_service, estimate_tokens, usd
from helixos.ai.models import AgentRunRecord, AgentRunStatus, AgentSessionRecord
from helixos.ai.providers import AgentPromptContext, get_agent_provider
from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.db.session import run_atomic
from helixos.eln.service import experiment_service
from helixos.errors import api_error
from helixos.observability import bind, current_request_id

logger = logging.getLogger("helixos.ai")

# In-memory retention caps: oldest sessions/runs are evicted first.
MAX_RETAINED_SESSIONS = 1_000
MAX_RETAINED_RUNS = 5_000

PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / "eln_copilot.md"

# Characters added to the prompt estimate for the tool summary the run appends.
TOOL_CONTEXT_ALLOWANCE = 200


@dataclass(frozen=True)
class RunTicket:
    """A run that passed every pre-flight check and holds budget until it settles."""

    session: AgentSessionRecord
    reservation: Reservation
    prompt_chars: int


class AgentService:
    """Coordinates agent sessions and streaming runs."""

    def __init__(self) -> None:
        self._sessions: OrderedDict[str, AgentSessionRecord] = OrderedDict()
        self._runs: OrderedDict[str, AgentRunRecord] = OrderedDict()

    @staticmethod
    def _evict(store: OrderedDict, limit: int) -> None:
        while len(store) > limit:
            store.popitem(last=False)

    def create_session(self, organization_id: str, actor: Actor) -> AgentSessionRecord:
        """Create an agent session scoped to a tenant."""
        organization_service.require_access(actor, organization_id)
        ratelimit.enforce(
            "ai_session",
            actor.subject,
            limits.rate_limit_settings().ai_session_per_minute,
        )
        session = AgentSessionRecord.create(organization_id)
        self._sessions[session.id] = session
        self._evict(self._sessions, MAX_RETAINED_SESSIONS)
        # Sync method behind a sync endpoint — FastAPI already runs it in a
        # threadpool, so the blocking audit write never touches the event loop.
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
            raise api_error(
                status_code=404, code="not_found", message="Agent session not found"
            )
        return session

    def authorize_session(self, session_id: str, actor: Actor):
        """Resolve a session and verify tenant access before any streaming starts."""
        session = self.get_session(session_id)
        organization_service.require_access(actor, session.organization_id)
        return session

    def preflight(self, session_id: str, message: str, actor: Actor) -> RunTicket:
        """Everything that can refuse a run, done before any byte is streamed.

        Blocking (it reads the spend ledger): call it from a worker thread. Raises
        the normal error envelope (404/403/422/429); on success the returned ticket
        holds budget that ``stream_run`` settles when the run ends.
        """
        session = self.authorize_session(session_id, actor)

        ai = limits.ai_limit_settings()
        if len(message) > ai.max_input_chars:
            raise api_error(
                status_code=422,
                code="message_too_long",
                message=(
                    f"Message is {len(message)} characters; the limit is {ai.max_input_chars}."
                ),
                details={"limit": ai.max_input_chars, "length": len(message)},
            )

        rates = limits.rate_limit_settings()
        ratelimit.enforce(
            "ai_run",
            actor.subject,
            rates.ai_run_actor_per_minute,
            message="You are starting agent runs too quickly. Wait a moment and try again.",
        )
        ratelimit.enforce(
            "ai_run_org",
            session.organization_id,
            rates.ai_run_org_per_minute,
            message="Your organization is starting agent runs too quickly. Try again shortly.",
        )

        prompt_chars = len(self._load_system_prompt()) + len(message) + TOOL_CONTEXT_ALLOWANCE
        reservation = budget_service.reserve(
            organization_id=session.organization_id,
            user_id=actor.subject,
            prompt_chars=prompt_chars,
        )
        return RunTicket(session=session, reservation=reservation, prompt_chars=prompt_chars)

    async def stream_run(
        self,
        session_id: str,
        message: str,
        actor: Actor,
        *,
        experiment_id: str | None = None,
        experiment_title: str | None = None,
        sequence_length: int | None = None,
        ticket: RunTicket | None = None,
    ) -> AsyncIterator[str]:
        """Execute an agent run and yield SSE frames."""
        if ticket is None:
            ticket = await run_in_threadpool(self.preflight, session_id, message, actor)
        session = ticket.session

        try:
            async for frame in self._run(
                ticket=ticket,
                session_id=session_id,
                message=message,
                actor=actor,
                experiment_id=experiment_id,
                experiment_title=experiment_title,
                sequence_length=sequence_length,
            ):
                yield frame
        finally:
            # Every exit (done, error, disconnect) has already settled; this only
            # frees the hold if something failed before settlement could run.
            budget_service.release(ticket.reservation)
            logger.debug("run budget released", extra={"organization_id": session.organization_id})

    async def _run(
        self,
        *,
        ticket: RunTicket,
        session_id: str,
        message: str,
        actor: Actor,
        experiment_id: str | None,
        experiment_title: str | None,
        sequence_length: int | None,
    ) -> AsyncIterator[str]:
        session = ticket.session
        run = AgentRunRecord.create(session_id, message)
        bind(run_id=run.id)
        logger.info("agent run started", extra={"session_id": session_id})
        self._runs[run.id] = run
        self._evict(self._runs, MAX_RETAINED_RUNS)
        run.status = AgentRunStatus.RUNNING
        await run_in_threadpool(
            audit_service.record,
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
            run.completed_at = datetime.now(timezone.utc)
            logger.info("agent run completed", extra={"tokens": run.token_count})
            # Settle spend and write the completion event in one transaction, and
            # do both before announcing completion, so a client that sees `done`
            # can rely on the usage and the audit event being durable.
            await run_in_threadpool(
                self._settle_and_audit,
                ticket,
                run,
                actor,
                "ai.run_completed",
                {"session_id": session_id, "event_count": len(run.events), "token_count": run.token_count},
            )
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected mid-stream: don't leave the run RUNNING, and
            # charge what it consumed.
            run.status = AgentRunStatus.CANCELLED
            run.completed_at = datetime.now(timezone.utc)
            logger.warning("agent run cancelled", extra={"tokens": run.token_count})
            self._settle_best_effort(
                ticket,
                run,
                actor,
                "ai.run_cancelled",
                {"session_id": run.session_id, "token_count": run.token_count},
            )
            raise
        except Exception as exc:  # noqa: BLE001 - surface agent failures as SSE errors
            run.status = AgentRunStatus.FAILED
            run.error = str(exc)
            logger.error("agent run failed", exc_info=True)
            await run_in_threadpool(
                self._settle_and_audit,
                ticket,
                run,
                actor,
                "ai.run_failed",
                {"session_id": session_id, "error": str(exc)},
            )
            yield self._sse(
                "error",
                {"message": str(exc), "run_id": run.id, "request_id": current_request_id()},
            )
            yield self._sse("done", {"run_id": run.id, "status": run.status})
            return

        done_payload = {
            "run_id": run.id,
            "status": AgentRunStatus.COMPLETED,
            "provider": run.provider,
            "usage": {
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "estimated": run.usage_estimated,
            },
        }
        run.events.append({"event": "done", "data": done_payload})
        yield self._sse("done", done_payload)

    # ------------------------------------------------------------------ #
    # Spend accounting
    # ------------------------------------------------------------------ #
    @staticmethod
    def _measure(ticket: RunTicket, run: AgentRunRecord) -> tuple[str, int, int, bool]:
        """(provider, input tokens, output tokens, estimated?) for a finished run."""
        if run.provider is None:
            return "none", 0, 0, False  # failed before any model was called: free
        reported = run.usage
        if reported is not None:
            return run.provider, reported.input_tokens, reported.output_tokens, False
        # The provider reported nothing: assume the full prompt and what streamed back.
        return (
            run.provider,
            estimate_tokens(ticket.prompt_chars),
            estimate_tokens(run.output_chars),
            True,
        )

    def _settle_and_audit(
        self,
        ticket: RunTicket,
        run: AgentRunRecord,
        actor: Actor,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        """Record the run's spend and its terminal audit event in one transaction."""
        provider, input_tokens, output_tokens, estimated = self._measure(ticket, run)

        def work() -> None:
            record = budget_service.record(
                ticket.reservation,
                run_id=run.id,
                provider=provider,
                model=run.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated=estimated,
                status=str(run.status),
            )
            run.input_tokens, run.output_tokens = input_tokens, output_tokens
            run.cost_micros, run.usage_estimated = record.cost_micros, estimated
            audit_service.record(
                organization_id=ticket.session.organization_id,
                actor=actor,
                event_type=event_type,
                resource_type="agent_run",
                resource_id=run.id,
                payload={
                    **payload,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": usd(record.cost_micros),
                    "usage_estimated": estimated,
                },
            )

        try:
            run_atomic(work)
        finally:
            # Only after the transaction has committed or definitively failed.
            budget_service.release(ticket.reservation)

    def _settle_best_effort(
        self,
        ticket: RunTicket,
        run: AgentRunRecord,
        actor: Actor,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        # Synchronous on purpose: this runs while the task is being cancelled,
        # when awaiting would be interrupted again.
        try:
            self._settle_and_audit(ticket, run, actor, event_type, payload)
        except Exception:  # noqa: BLE001 - never mask the cancellation itself
            logger.error("could not settle cancelled run", exc_info=True)

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
        experiments = await run_in_threadpool(
            experiment_service.list_experiments, actor
        )
        visible = [
            item for item in experiments if item.organization_id == organization_id
        ]

        tool_payload = {
            "tool": "list_experiments",
            "status": "completed",
            "count": len(visible),
        }
        run.events.append({"event": "tool_call", "data": tool_payload})
        await self._record_tool_call(
            organization_id=organization_id,
            actor=actor,
            run_id=run.id,
            tool_payload=tool_payload,
        )
        yield self._sse("tool_call", tool_payload)

        provider = get_agent_provider()
        provider_payload = {
            "tool": "provider",
            "status": "running",
            "name": provider.name,
        }
        run.events.append({"event": "tool_call", "data": provider_payload})
        await self._record_tool_call(
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

        run.provider = provider.name
        run.model = provider.model
        ai = limits.ai_limit_settings()
        try:
            async with asyncio.timeout(ai.run_timeout_seconds):
                async for token in provider.stream_response(
                    prompt_context, max_output_tokens=ai.max_output_tokens
                ):
                    # Count tokens rather than retaining each one for the life of the process.
                    run.token_count += 1
                    run.output_chars += len(token)
                    yield self._sse("token", {"content": token, "run_id": run.id})
        except TimeoutError:
            raise RuntimeError(
                f"Agent run exceeded the {ai.run_timeout_seconds}s time limit"
            ) from None
        finally:
            # Whatever the provider billed, even if the stream ended early.
            run.usage = provider.usage

    async def _record_tool_call(
        self,
        *,
        organization_id: str,
        actor: Actor,
        run_id: str,
        tool_payload: dict[str, object],
    ) -> None:
        await run_in_threadpool(
            audit_service.record,
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
