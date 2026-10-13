"""MCP connector registry routes."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends

from helixos import limits, ratelimit
from helixos.auth.schemas import Actor
from helixos.auth.service import get_current_actor
from helixos.mcp.schemas import (
    ConnectorJobRequest,
    ConnectorJobResult,
    ConnectorManifest,
)
from helixos.mcp.service import mcp_bridge_client

router = APIRouter(prefix="/mcp", tags=["mcp"])

REGISTRY_PATH = Path(__file__).resolve().parents[4] / "mcp" / "registry.json"

_FALLBACK_CONNECTORS: tuple[ConnectorManifest, ...] = (
    ConnectorManifest(
        id="biopython-local",
        name="BioPython Local",
        description="Local sequence parsing and molecular biology utilities.",
        scopes=["sequence:read", "sequence:analyze"],
        transport="stdio",
        enabled_by_default=True,
    ),
)


def _load_connectors() -> tuple[ConnectorManifest, ...]:
    """Load connector manifests from mcp/registry.json (single source of truth).

    Falls back to the built-in BioPython manifest when the registry file is
    absent (e.g. partial packaged installs).
    """
    if not REGISTRY_PATH.exists():
        return _FALLBACK_CONNECTORS
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return tuple(ConnectorManifest(**entry) for entry in registry.get("connectors", []))


CONNECTORS: tuple[ConnectorManifest, ...] = _load_connectors()


@router.get("/connectors", response_model=list[ConnectorManifest])
def list_connectors(
    _actor: Actor = Depends(get_current_actor),
) -> list[ConnectorManifest]:
    """Return registered MCP connectors."""
    return list(CONNECTORS)


@router.post("/jobs", response_model=ConnectorJobResult, status_code=200)
async def run_connector_job(
    payload: ConnectorJobRequest,
    actor: Actor = Depends(get_current_actor),
) -> ConnectorJobResult:
    """Dispatch a connector tool through the desktop MCP bridge."""
    ratelimit.enforce("mcp_job", actor.subject, limits.rate_limit_settings().mcp_job_per_minute)
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
