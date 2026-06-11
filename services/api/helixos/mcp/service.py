"""MCP job dispatch service."""

from __future__ import annotations

import os
from typing import Any

import httpx

from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.errors import api_error
from helixos.mcp.schemas import ConnectorJobRequest, ConnectorJobResult


class MCPBridgeClient:
    """Calls the desktop MCP bridge when available."""

    def __init__(self, bridge_url: str | None) -> None:
        self._bridge_url = bridge_url.rstrip("/") if bridge_url else None

    @classmethod
    def from_env(cls) -> "MCPBridgeClient":
        return cls(os.getenv("HELIX_MCP_BRIDGE_URL"))

    @property
    def available(self) -> bool:
        return bool(self._bridge_url)

    async def run_tool(self, request: ConnectorJobRequest, actor: Actor) -> ConnectorJobResult:
        """Dispatch a connector tool call through the desktop bridge."""
        if not self._bridge_url:
            raise api_error(
                status_code=503,
                code="bridge_unavailable",
                message="MCP bridge is unavailable. Launch HelixOS desktop to run stdio connectors.",
            )

        organization_id = actor.organization_ids[0] if actor.organization_ids else "unknown"
        audit_service.record(
            organization_id=organization_id,
            actor=actor,
            event_type="mcp.job_started",
            resource_type="mcp_connector",
            resource_id=request.connector_id,
            payload={
                "tool": request.tool,
                "arguments": request.arguments,
            },
        )

        url = f"{self._bridge_url}/connectors/{request.connector_id}/tools/{request.tool}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json={"arguments": request.arguments})
        except httpx.HTTPError as exc:
            audit_service.record(
                organization_id=organization_id,
                actor=actor,
                event_type="mcp.job_failed",
                resource_type="mcp_connector",
                resource_id=request.connector_id,
                payload={"tool": request.tool, "error": str(exc)},
            )
            raise api_error(
                status_code=503,
                code="bridge_unreachable",
                message="Unable to reach the MCP bridge",
                details={"reason": str(exc)},
            ) from exc

        if response.status_code >= 400:
            detail: dict[str, Any]
            try:
                detail = response.json()
            except ValueError:
                detail = {"message": response.text}
            audit_service.record(
                organization_id=organization_id,
                actor=actor,
                event_type="mcp.job_failed",
                resource_type="mcp_connector",
                resource_id=request.connector_id,
                payload={"tool": request.tool, "error": detail},
            )
            raise api_error(
                status_code=502,
                code="bridge_error",
                message="MCP bridge rejected the connector job",
                details=detail,
            )

        payload = response.json()
        result = ConnectorJobResult(
            connector_id=request.connector_id,
            tool=request.tool,
            status=str(payload.get("status", "completed")),
            result=payload.get("result"),
        )
        audit_service.record(
            organization_id=organization_id,
            actor=actor,
            event_type="mcp.job_completed",
            resource_type="mcp_connector",
            resource_id=request.connector_id,
            payload={
                "tool": request.tool,
                "status": result.status,
                "result": result.result,
            },
        )
        return result


mcp_bridge_client = MCPBridgeClient.from_env()
