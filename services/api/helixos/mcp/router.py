"""MCP connector registry routes."""

from fastapi import APIRouter, Depends

from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor
from helixos.mcp.schemas import ConnectorManifest

router = APIRouter(prefix="/mcp", tags=["mcp"])

CONNECTORS: tuple[ConnectorManifest, ...] = (
    ConnectorManifest(
        id="biopython-local",
        name="BioPython Local",
        description="Local sequence parsing and molecular biology utilities.",
        scopes=["sequence:read", "sequence:analyze"],
        transport="stdio",
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
