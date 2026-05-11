"""Pydantic schemas for MCP connector metadata."""

from pydantic import BaseModel


class ConnectorManifest(BaseModel):
    """Public manifest for a scientific MCP connector."""

    id: str
    name: str
    description: str
    scopes: list[str]
    transport: str
    enabled_by_default: bool = False
