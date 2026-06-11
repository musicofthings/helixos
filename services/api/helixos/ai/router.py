"""AI agent API routes."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from helixos.ai.schemas import AgentRunCreate, AgentSession, AgentSessionCreate
from helixos.ai.service import agent_service
from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/sessions", response_model=AgentSession, status_code=201)
def create_session(payload: AgentSessionCreate, actor: Actor = Depends(get_current_actor)) -> AgentSession:
    """Create an agent session for a tenant."""
    session = agent_service.create_session(payload.organization_id, actor)
    return AgentSession(
        id=session.id,
        organization_id=session.organization_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post("/runs")
async def start_run(payload: AgentRunCreate, actor: Actor = Depends(get_current_actor)) -> StreamingResponse:
    """Start an agent run and stream SSE events."""

    async def event_stream() -> AsyncIterator[str]:
        async for frame in agent_service.stream_run(
            payload.session_id,
            payload.message,
            actor,
            experiment_id=payload.context.experiment_id,
            experiment_title=payload.context.experiment_title,
            sequence_length=payload.context.sequence_length,
        ):
            yield frame

    return StreamingResponse(event_stream(), media_type="text/event-stream")
