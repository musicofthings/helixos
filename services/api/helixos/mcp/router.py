"""MCP connector registry routes."""

from fastapi import APIRouter, Depends

from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor
from helixos.mcp.schemas import ConnectorJobRequest, ConnectorJobResult, ConnectorManifest
from helixos.mcp.service import mcp_bridge_client

router = APIRouter(prefix="/mcp", tags=["mcp"])

CONNECTORS: tuple[ConnectorManifest, ...] = (
    ConnectorManifest(
        id="biopython-local",
        name="BioPython Local",
        description="Local sequence parsing and molecular biology utilities.",
        scopes=["sequence:read", "sequence:analyze"],
        transport="stdio",
        enabled_by_default=True,
    ),
    ConnectorManifest(
        id="pubmed",
        name="PubMed",
        description="Literature search connector for biomedical references.",
        scopes=["literature:search"],
        transport="http",
    ),
)


@router.get("/connectors", response_model=list[ConnectorManifest])
def list_connectors(_actor: Actor = Depends(get_current_actor)) -> list[ConnectorManifest]:
    """Return registered MCP connectors."""
    return list(CONNECTORS)


@router.post("/jobs", response_model=ConnectorJobResult, status_code=200)
async def run_connector_job(
    payload: ConnectorJobRequest,
    actor: Actor = Depends(get_current_actor),
) -> ConnectorJobResult:
    """Dispatch a connector tool through the desktop MCP bridge."""
    known_ids = {connector.id for connector in CONNECTORS}
    if payload.connector_id not in known_ids:
        from helixos.errors import api_error

        raise api_error(
            status_code=404,
            code="not_found",
            message="Connector not found",
            details={"connector_id": payload.connector_id},
        )
    return await mcp_bridge_client.run_tool(payload, actor)
