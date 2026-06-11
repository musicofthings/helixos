# Audit Trail

The audit module stores immutable, hash-chained events for regulated actions across [AI](ai.md) and [MCP](mcp.md) workflows.

**Related:** [auth.md](auth.md) · [ai.md](ai.md) · [mcp.md](mcp.md) · [SYSTEM_ARCHITECTURE.md](../../SYSTEM_ARCHITECTURE.md)

## What Gets Recorded

| Event type | Source |
| --- | --- |
| `ai.session_created` | AI session create |
| `ai.run_started` | Agent run begin |
| `ai.tool_call` | Agent tool invocation |
| `ai.run_completed` / `ai.run_failed` | Agent run end |
| `mcp.job_started` / `mcp.job_completed` / `mcp.job_failed` | MCP job dispatch |

## User Surface

- Workspace sidebar shows recent audit events from `GET /api/v1/audit/events`
- Falls back to local activity log when the API returns no events

## Storage Backends

| Backend | When used |
| --- | --- |
| In-memory | CI and API dev without `HELIX_DATABASE_URL` |
| SQLite | Local dev (`.data/helixos-dev.db`) and [desktop](desktop.md) |
| PostgreSQL | Server deployments via docker-compose |

Each organization maintains its own hash chain. Every event stores `sequence_number`, `previous_hash`, and `event_hash`.

## API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/audit/events?organization_id=` | List events for actor-visible org |
| `GET` | `/api/v1/audit/verify?organization_id=` | Verify hash chain integrity |

## Configuration

**Browser / server dev:**

```bash
export HELIX_DATABASE_URL=sqlite:///$(pwd)/.data/helixos-dev.db
npm run dev:api
```

**Postgres:**

```bash
docker compose up -d postgres
export HELIX_DATABASE_URL=postgresql+psycopg://helixos:helixos@127.0.0.1:5432/helixos
```

**Desktop:** sidecar sets `HELIX_DATABASE_URL` to SQLite under `.data/helixos-dev.db` (dev) or `<userData>/helixos/helixos.db` (packaged). See [desktop.md](desktop.md).

## Permissions

Listing and verification require bearer authentication and respect [auth](auth.md) tenant isolation. SQL storage uses append-only inserts with per-organization sequence numbers.

Hash computation uses canonical UTC timestamps so chains verify consistently across Postgres and SQLite.

## Verify Example

```bash
curl -H "Authorization: Bearer org-demo-token" \
  "http://127.0.0.1:8000/api/v1/audit/verify?organization_id=org_demo"
```
