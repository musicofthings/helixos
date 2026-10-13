# HelixOS Documentation

Read these documents in order when onboarding to the platform. Each layer builds on the previous one.

## 1. Platform scope

| Document | What you learn |
| --- | --- |
| [../README.md](../README.md) | What HelixOS is, repo layout, quick start |
| [../DOMAIN_GLOSSARY.md](../DOMAIN_GLOSSARY.md) | Lab-domain terms (ELN, MCP, organization, etc.) |
| [OVERVIEW.md](OVERVIEW.md) | Product scope, MVP vs planned, who uses what |

## 2. How the system fits together

| Document | What you learn |
| --- | --- |
| [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) | Runtime components, domain map, request flow |
| [../API_CONTRACTS.md](../API_CONTRACTS.md) | REST endpoints, auth, example payloads |
| [../SCHEMA_GUIDE.md](../SCHEMA_GUIDE.md) | JSON Schema conventions shared by API and clients |

## 3. Runtime surfaces

| Document | What you learn |
| --- | --- |
| [modules/desktop.md](modules/desktop.md) | Electron shell, API sidecar, MCP bridge, packaging, releases |
| [SITE.md](SITE.md) | Public landing site (Cloudflare Pages) and download links |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Environments, startup validation, API image, web proxy |
| [BETA_LAUNCH_PLAN.md](BETA_LAUNCH_PLAN.md) | Production-readiness gaps and beta sequencing |
| [modules/auth.md](modules/auth.md) | Organizations, actors, tenant isolation |

The web app (`apps/web`) is the shared workspace UI. In browser dev it talks to the API on port **8000**. In desktop dev it loads from port **3000** and talks to the sidecar on **8765** via preload/query params.

## 4. Domain modules (backend + UI)

| Module | Doc | API prefix | Depends on |
| --- | --- | --- | --- |
| ELN | [modules/eln.md](modules/eln.md) | `/api/v1/experiments` | auth |
| Molecular | [modules/molecular.md](modules/molecular.md) | `/api/v1/sequences` | auth |
| AI copilot | [modules/ai.md](modules/ai.md) | `/api/v1/ai` | auth, audit |
| MCP connectors | [modules/mcp.md](modules/mcp.md) | `/api/v1/mcp` | auth, audit, desktop (for stdio jobs) |
| Audit trail | [modules/audit.md](modules/audit.md) | `/api/v1/audit` | auth, database |

Full module index: [modules/README.md](modules/README.md).

Planned domains (architecture only today): inventory, biobank, workflows — see [OVERVIEW.md](OVERVIEW.md).

## 5. Cross-cutting flows

```txt
User (browser or Electron)
  → apps/web workspace
  → packages/api-client
  → services/api (FastAPI)
       ├─ auth: resolve actor + organization scope
       ├─ eln / molecular / …: domain logic
       ├─ ai: agent sessions + SSE runs → audit events
       └─ mcp: connector jobs → desktop bridge → stdio servers → audit events
  → audit store (memory | SQLite | Postgres)
```

Detailed sequence diagrams live in [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md).

## 6. Contributing and agents

| Document | What you learn |
| --- | --- |
| [../AGENTS.md](../AGENTS.md) | Module layout, definition of done, agent rules |
| [../agents/module_scaffold.md](../agents/module_scaffold.md) | Checklist for adding a new domain module |
| [../prompts/eln_copilot.md](../prompts/eln_copilot.md) | System prompt used by the stub/OpenAI agent provider |

## Quick commands

```bash
npm run setup          # first-time install
npm run dev:browser    # API :8000 + web :3000
npm run dev:desktop    # Electron + sidecar :8765 + MCP :8766 + web :3000
npm run test:api       # backend pytest suite
```

## Database migrations

SQL-backed deployments (SQLite, PostgreSQL) are versioned by `services/api/helixos/db/migrations.py`. The API applies pending migrations at startup (`init_db`), once per process; applied versions live in `helix_schema_migrations`.

```bash
cd services/api
HELIX_DATABASE_URL=... python -m helixos.db.migrations status
HELIX_DATABASE_URL=... python -m helixos.db.migrations upgrade
```

To change the schema, append a `(version, fn)` entry to `MIGRATIONS` (never edit an applied one) and use `op.batch_alter_table` for anything SQLite cannot `ALTER`. `0001_baseline` creates tables from the current ORM models, so later migrations must be idempotent (`column_exists` / `index_exists`). Databases created before versioning are adopted by the baseline automatically.

## List pagination

ELN list endpoints (`workspaces`, `projects`, `protocols`, `experiments`, experiment `versions`, `samples`, sample `datasets`) accept `limit` (1–500, default 100) and `offset` (default 0). Responses remain plain JSON arrays; page metadata is in headers: `X-Total-Count` always, and `X-Next-Offset` while more items remain (CORS exposes both). `@helixos/api-client` list methods follow `X-Next-Offset` automatically (500 per request) and return the full list.

The window is applied in the database query: stores expose `page_*` methods that take a `PageRequest` and return a `PageResult` (items plus total), ordered by `(created_at, id)` (versions by `version_number`). Visibility is resolved once in the service — organization members see their orgs, share grantees see only shared workspaces (and the projects/experiments inside them) — and passed to the store as `organization_ids` plus shared workspace/project ids, so one `WHERE org IN (…) OR shared IN (…)` query serves both. Composite indexes matching that `ORDER BY` are created by migration `0002_eln_list_indexes`. The total comes from a `COUNT(*)`, which still scans the matching index range.

Behaviour note: listing an organization you do not belong to returns 403 unless you hold a share in it; a grantee of an empty shared workspace now gets an empty page (previously 403).

## Logging and request IDs

The API logs one JSON object per line to stderr (`HELIX_LOG_FORMAT=text` for readable dev output, `HELIX_LOG_LEVEL` for the level). Each request gets a `request_id` — an inbound `X-Request-ID` matching `[A-Za-z0-9._-]{1,64}` is honored, otherwise one is generated — returned in the `X-Request-ID` response header (exposed via CORS) and in `error.request_id` of every error envelope. All log records emitted while handling the request, including threadpool work, carry `request_id` and, once authenticated, `actor`. Agent runs add `run_id`, connector jobs add `job_id`, and `helixos.access` logs method, path (never the query string), status and `duration_ms`; `/health` logs at debug. Unhandled exceptions are logged with a traceback and returned as a generic `internal_error` envelope. The desktop sidecar runs uvicorn with its own access log off.

Request IDs are not written into audit events (they would change hash-chained payloads); correlate through `resource_id` and timestamps.

The web client surfaces the request ID: `HelixOSApiError.requestId` (from `error.request_id`, falling back to the `X-Request-ID` header), and user-facing failure messages render as `message (ref req_…)` via `apps/web/lib/error-message.ts`. Agent-run `error` SSE frames also carry `request_id`.


## Smoke tests and agent evals

`services/api/evals/run.py` boots a throwaway API (fresh SQLite database, so migrations run from scratch) and drives it over HTTP.

```bash
cd services/api
python evals/run.py                        # everything
python evals/run.py --suite smoke          # or: --suite agent
python evals/run.py --base-url http://127.0.0.1:8000 --json report.json   # existing API (writes data)
```

- **Smoke:** health, migrations and list indexes, request IDs and the error envelope, CORS, the full workspace → dataset hierarchy, version locking, pagination, share/invite access (including cross-org editors being audited), audit hash chains, the MCP connector over stdio, and log correlation.
- **Agent evals:** properties of the system around the model, so they are meaningful for any provider: stream protocol order, grounding of tool results in what the API shows, tenant isolation (including a multi-org user in a single-org session), prompt-injection attempts, audit trail completeness, authorization before streaming, odd input, 10 parallel runs, and a latency budget. Checks that depend on the stub's deterministic text are skipped for other providers.

CI runs the suite in the `api` job and uploads the JSON report.
