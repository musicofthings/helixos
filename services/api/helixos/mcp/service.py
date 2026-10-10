"""MCP job dispatch service."""

from __future__ import annotations

import logging
import os
from uuid import uuid4
from typing import Any

import httpx

from starlette.concurrency import run_in_threadpool

from helixos.audit.service import audit_service
from helixos.auth.schemas import Actor
from helixos.auth.service import organization_service
from helixos.errors import api_error
from helixos.observability import bind
from helixos.mcp.schemas import ConnectorJobRequest, ConnectorJobResult


logger = logging.getLogger("helixos.mcp")


class MCPBridgeClient:
    """Calls the desktop MCP bridge when available."""

    def __init__(self, bridge_url: str | None, bridge_token: str | None = None) -> None:
        self._bridge_url = bridge_url.rstrip("/") if bridge_url else None
        self._bridge_token = bridge_token

    @classmethod
    def from_env(cls) -> "MCPBridgeClient":
        return cls(
            os.getenv("HELIX_MCP_BRIDGE_URL"), os.getenv("HELIX_MCP_BRIDGE_TOKEN")
        )

    @property
    def available(self) -> bool:
        return bool(self._bridge_url)

    async def run_tool(
        self, request: ConnectorJobRequest, actor: Actor
    ) -> ConnectorJobResult:
        """Dispatch a connector tool call through the desktop bridge."""
        organization_id = request.organization_id
        organization_service.require_access(actor, organization_id)

        job_id = f"job_{uuid4().hex[:16]}"
        bind(job_id=job_id)
        logger.info(
            "connector job dispatching",
            extra={"connector_id": request.connector_id, "tool": request.tool},
        )

        if not self._bridge_url:
            raise api_error(
                status_code=503,
                code="bridge_unavailable",
                message="MCP bridge is unavailable. Launch HelixOS desktop to run stdio connectors.",
            )

        await run_in_threadpool(
            audit_service.record,
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

        url = (
            f"{self._bridge_url}/connectors/{request.connector_id}/tools/{request.tool}"
        )
        headers = (
            {"x-helix-bridge-token": self._bridge_token} if self._bridge_token else {}
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url, json={"arguments": request.arguments}, headers=headers
                )
        except httpx.HTTPError as exc:
            logger.error("connector bridge unreachable", extra={"reason": str(exc)})
            await run_in_threadpool(
                audit_service.record,
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
            await run_in_threadpool(
                audit_service.record,
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
        await run_in_threadpool(
            audit_service.record,
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
