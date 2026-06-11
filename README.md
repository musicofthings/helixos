# HelixOS

AI-native Laboratory Management & Molecular Biology Platform.

HelixOS combines ELN, molecular biology tooling, AI copilots, MCP connectors, and a hash-chained audit trail in one workspace. It ships as a **browser stack** (Next.js + FastAPI) and a **desktop app** (Electron + local sidecar + MCP bridge).

**New here?** Read in order: [docs/OVERVIEW.md](docs/OVERVIEW.md) → [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) → [docs/README.md](docs/README.md).

**Resuming work?** Read [SESSION_HANDOVER.md](SESSION_HANDOVER.md) for current state, uncommitted changes, and production next steps.

## Current Status (June 2026)

Local dev is working end-to-end. The workspace UI is wired to the API for organizations, ELN create/list/status, sequence metadata, AI agent sessions (SSE), MCP connector jobs (desktop), and hash-chained audit events.

| Area | Status |
| --- | --- |
| Browser dev stack | Working (`npm run dev:browser`) |
| Desktop dev stack | Working (`npm run dev:desktop`) |
| API tests | 26 passing (`npm run test:api`) |
| Documentation | Connected hub at [docs/README.md](docs/README.md) |
| Production deploy | Not yet — see [SESSION_HANDOVER.md](SESSION_HANDOVER.md) |

**Not production-ready yet:** durable ELN/inventory persistence, JWT/OIDC auth, Postgres migrations, packaged desktop release pipeline, and inventory/biobank/workflows backend modules.

## Repository Layout

```txt
apps/web/       Next.js workspace UI
apps/desktop/   Electron shell + sidecar + MCP bridge
services/api/   FastAPI backend (helixos.* domains)
packages/       Shared TypeScript (api-client, types)
schemas/        JSON Schema contracts
docs/           Documentation hub — start at docs/README.md
mcp/            Connector manifests and stdio servers
prompts/        Agent system prompts
agents/         Contributor playbooks
scripts/        Dev setup and orchestration scripts
```

## Quick Start

```bash
npm run setup        # once: venv, npm deps, .env.local
npm run dev:browser  # API :8000 + web :3000
npm run dev:desktop  # Electron + sidecar :8765 + MCP :8766 + web :3000
npm run test:api     # pytest (26 tests)
```

| Surface | URL |
| --- | --- |
| Web UI | http://127.0.0.1:3000 |
| API (browser) | http://127.0.0.1:8000 |
| API (desktop sidecar) | http://127.0.0.1:8765 |
| MCP bridge (desktop) | http://127.0.0.1:8766 |

Demo bearer tokens:

| Token | Organizations |
| --- | --- |
| `org-demo-token` | `org_demo` |
| `demo-admin-token` | `org_demo`, `org_qc` |

Set `HELIX_DATABASE_URL=sqlite:///$(pwd)/.data/helixos-dev.db` for persistent audit in browser dev (desktop sets this automatically).

## Documentation Map

| Topic | Document |
| --- | --- |
| Doc index & reading order | [docs/README.md](docs/README.md) |
| MVP scope & run modes | [docs/OVERVIEW.md](docs/OVERVIEW.md) |
| Architecture & flows | [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) |
| REST API reference | [API_CONTRACTS.md](API_CONTRACTS.md) |
| JSON Schema rules | [SCHEMA_GUIDE.md](SCHEMA_GUIDE.md) |
| Domain vocabulary | [DOMAIN_GLOSSARY.md](DOMAIN_GLOSSARY.md) |
| Contributor / agent rules | [AGENTS.md](AGENTS.md) |
| Module deep-dives | [docs/modules/](docs/modules/) |
| Session handover | [SESSION_HANDOVER.md](SESSION_HANDOVER.md) |

## MVP Modules

Implemented (UI + API where noted):

- [Auth & organizations](docs/modules/auth.md) — demo tokens + tenant scoping
- [ELN experiment drafts](docs/modules/eln.md) — create, list, status PATCH, audit events
- [Sequence metadata](docs/modules/molecular.md) — API metadata + client-side analyzer
- [AI copilot (SSE)](docs/modules/ai.md) — sessions, streaming runs, audit
- [MCP connectors](docs/modules/mcp.md) — BioPython local via desktop bridge
- [Audit trail](docs/modules/audit.md) — hash-chained events (memory / SQLite / Postgres)
- [Desktop shell](docs/modules/desktop.md) — Electron + sidecar + MCP bridge

**Prototype only:** inventory tab (local state, no API). Planned: biobank, workflows — see [docs/OVERVIEW.md](docs/OVERVIEW.md).

## Agent Rules

Read [AGENTS.md](AGENTS.md) before changing code. Preserve typed schemas, API contracts, tests, and module documentation.
