# MCP Connector Framework

The MCP module manages scientific tool manifests, connector scopes, and job dispatch. Stdio servers run on the **desktop** host; the API forwards jobs through a local HTTP bridge.

**Related:** [desktop.md](desktop.md) · [molecular.md](molecular.md) · [audit.md](audit.md) · [auth.md](auth.md)

## Architecture

```txt
apps/web  →  POST /api/v1/mcp/jobs  →  services/api
                                           ↓
                              HELIX_MCP_BRIDGE_URL (desktop sets this)
                                           ↓
                              apps/desktop MCP bridge :8766
                                           ↓
                              mcp/servers/*/server.py (stdio, NDJSON)
```

Browser-only dev (`npm run dev:browser`) cannot run stdio connector jobs — use [desktop.md](desktop.md).

## Connector Types

| ID | Transport | Status |
| --- | --- | --- |
| `biopython-local` | stdio | Implemented |
| PubMed, BLAST, AlphaFold, NCBI, UniProt, Internal SOP, Vector DB | http / planned | Registry metadata only |

Manifests live under `mcp/`.

## Local Stdio Server

`mcp/servers/biopython_local/server.py` exposes newline-delimited JSON tools:

- `analyze_sequence` — length and GC percent

The [desktop shell](desktop.md) spawns this process and exposes it through the MCP bridge consumed by the API.

## User Surface

Workspace **Connectors** tab:

1. Lists connectors from `GET /api/v1/mcp/connectors`
2. Toggle enable / run job → `POST /api/v1/mcp/jobs`
3. Command palette (⌘K) includes “Analyze current sequence with BioPython Local”

## API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/mcp/connectors` | List registered manifests |
| `POST` | `/api/v1/mcp/jobs` | Dispatch tool via `HELIX_MCP_BRIDGE_URL` |

Example job request:

```json
{
  "connector_id": "biopython-local",
  "tool": "analyze_sequence",
  "arguments": {
    "sequence": "ATGCGC"
  }
}
```

Requires `HELIX_MCP_BRIDGE_URL` (set automatically by the desktop sidecar).

## Security Rules

Connectors must declare scopes before execution. Jobs with file, network, or compute access must be sandboxed and auditable. The bridge listens on `127.0.0.1` only.

## Audit And Permissions

Connector discovery and job dispatch require [auth](auth.md). Jobs record [audit events](audit.md): `mcp.job_started`, `mcp.job_completed`, `mcp.job_failed`.
