"""AI agent API routes."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from starlette.concurrency import run_in_threadpool

from helixos.ai.budget import budget_service
from helixos.ai.schemas import (
    AgentRunCreate,
    AgentSession,
    AgentSessionCreate,
    AiUsageSummary,
)
from helixos.ai.service import agent_service
from helixos.auth.roles import MEMBERS_MANAGE
from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor, organization_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/sessions", response_model=AgentSession, status_code=201)
def create_session(
    payload: AgentSessionCreate, actor: Actor = Depends(get_current_actor)
) -> AgentSession:
    """Create an agent session for a tenant."""
    session = agent_service.create_session(payload.organization_id, actor)
    return AgentSession(
        id=session.id,
        organization_id=session.organization_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post("/runs")
async def start_run(
    payload: AgentRunCreate, actor: Actor = Depends(get_current_actor)
) -> StreamingResponse:
    """Start an agent run and stream SSE events."""
    # Refuse before headers are sent so 404/403/422/429 use the normal error
    # envelope. Reads the spend ledger, so it runs off the event loop.
    ticket = await run_in_threadpool(
        agent_service.preflight, payload.session_id, payload.message, actor
    )

    async def event_stream() -> AsyncIterator[str]:
        async for frame in agent_service.stream_run(
            payload.session_id,
            payload.message,
            actor,
            ticket=ticket,
            experiment_id=payload.context.experiment_id,
            experiment_title=payload.context.experiment_title,
            sequence_length=payload.context.sequence_length,
        ):
            yield frame

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # no-transform stops compressing proxies (Next's rewrite proxy gzips
            # otherwise and holds the whole stream until it ends); X-Accel-Buffering
            # does the same for nginx-style proxies.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/usage", response_model=AiUsageSummary)
def get_usage(
    organization_id: str, actor: Actor = Depends(get_current_actor)
) -> AiUsageSummary:
    """AI spend against the caps for an organization (admins only)."""
    organization_service.require_permission(actor, organization_id, MEMBERS_MANAGE)
    return AiUsageSummary(**budget_service.summary(organization_id, actor.subject))
