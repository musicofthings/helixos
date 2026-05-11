# MCP Connector Framework

The MCP module manages scientific tool manifests, connector scopes, sandbox configuration, and asynchronous job dispatch.

## Connector Types

- BioPython
- BLAST
- AlphaFold
- PubMed
- NCBI
- UniProt
- Internal SOP
- Vector DB

## Security Rules

Connectors must declare scopes before execution. Jobs with file, network, or compute access must be sandboxed and auditable.

## API Surface

- `GET /api/v1/mcp/connectors` lists registered connector manifests for authenticated callers.

## Audit And Permissions

Connector discovery requires a bearer token. Future job dispatch endpoints should check connector scopes against actor permissions and persist audit events for file, network, or compute access.
