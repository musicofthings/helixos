"""Pydantic schemas for MCP connector metadata."""

from typing import Any

from pydantic import BaseModel, Field


class ConnectorManifest(BaseModel):
    """Public manifest for a scientific MCP connector."""

    id: str
    name: str
    description: str
    scopes: list[str]
    transport: str
    enabled_by_default: bool = False


class ConnectorJobRequest(BaseModel):
    """Payload for invoking a connector tool."""

    connector_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConnectorJobResult(BaseModel):
    """Result of a connector tool invocation."""

    connector_id: str
    tool: str
    status: str
    result: Any | None = None
