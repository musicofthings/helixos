# HelixOS

AI-native Laboratory Management & Molecular Biology Platform.

HelixOS combines ELN, molecular biology tooling, AI copilots, MCP connectors, and a hash-chained audit trail in one workspace. It ships as a **browser stack** (Next.js + FastAPI) and a **desktop app** (Electron + local sidecar + MCP bridge).

**Website:** [helixos.pages.dev](https://helixos.pages.dev/) — product overview, light-pastel default theme, and macOS download.

**Download:** [Latest GitHub Release](https://github.com/musicofthings/helixos/releases/latest) (`HelixOS-mac-x64.dmg`; not Apple-notarized yet).

**New here?** Read in order: [docs/OVERVIEW.md](docs/OVERVIEW.md) → [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) → [docs/README.md](docs/README.md). Landing site notes: [docs/SITE.md](docs/SITE.md).

**Resuming work?** Read [SESSION_HANDOVER.md](SESSION_HANDOVER.md) for current state, uncommitted changes, and production next steps.

## Current Status (August 2026)

Local browser and desktop stacks work end-to-end. The shared web app (`apps/web`) powers both surfaces with a **Slack-style workspace shell**: workspaces are sidebar channels; create/select opens a workspace home; Lab notebook and other tools are scoped to the active workspace.

| Area | Status |
| --- | --- |
| Browser dev stack | Working (`npm run dev:browser`) |
| Desktop dev stack | Working (`npm run dev:desktop`) |
| Packaged desktop (local) | Working (`cd apps/desktop && npm run pack`) — static UI over loopback + API proxy/CORS |
| Public website | [`apps/site`](apps/site) → Cloudflare Pages ([docs/SITE.md](docs/SITE.md)) |
| Desktop releases | Tag `v*.*.*` → Actions builds macOS DMG → GitHub Releases |
| Workspace shell | Slack-style channels + workspace home + scoped lab notebook |
| Workspace share / invites | Working (viewer/editor grants, invite links) |
| ELN protocols library | In progress (CRUD + import stubs) |
| API tests | See `npm run test:api` |
| Documentation | Connected hub at [docs/README.md](docs/README.md) |
| Production deploy | Not yet — see [SESSION_HANDOVER.md](SESSION_HANDOVER.md) |

**Not production-ready yet:** JWT/OIDC auth, Postgres migrations for all environments, notarized desktop release pipeline, and inventory/biobank/workflows backend modules.

## Workspace UI (shared web + desktop)

Both `npm run dev:browser` and the desktop shell load the same Next.js app:

- **Sidebar — Workspaces** — channel list + create (`+`). Selecting a channel opens that workspace’s **home** (projects, recent experiments, Share / Delete / Open lab, Agent).
- **Sidebar — Tools** — Lab notebook (scoped to the active workspace), Protocols, Sequences, Inventory, Connectors.
- **Lab notebook** — Project → Experiment only for the active workspace (no nested workspace switcher).
- **Desktop extras** — API sidecar status badge, MCP stdio connectors (e.g. BioPython Local), packaged static export served over loopback with `/api` proxied to the sidecar.

## Repository Layout

```txt
apps/web/       Next.js workspace UI (browser + desktop)
apps/desktop/   Electron shell + sidecar + MCP bridge
apps/site/      Public landing site (Cloudflare Pages)
services/api/   FastAPI backend (helixos.* domains)
packages/       Shared TypeScript (api-client, types)
schemas/        JSON Schema contracts
docs/           Documentation hub — start at docs/README.md
mcp/            Connector manifests and stdio servers
prompts/        Agent system prompts
agents/         Contributor playbooks
scripts/        Dev setup and orchestration scripts
.github/        Pages deploy + desktop release workflows
```

## Quick Start

```bash
npm run setup        # once: venv, npm deps, .env.local
npm run dev:browser  # API :8000 + web :3000
npm run dev:desktop  # Electron + sidecar :8765 + MCP :8766 + web :3000
npm run test:api     # pytest
```

## How to use the public site

1. Open [helixos.pages.dev](https://helixos.pages.dev/).
2. Read the Product, How to use, Traction, and Investors sections.
3. Use the theme switcher in the header if you want to compare light and dark modes.
4. Click **Request investor deck** or **Latest desktop release** when you want to go deeper.

Packaged local desktop:

```bash
cd apps/desktop
npm run pack
open release/mac/HelixOS.app
```

Published macOS download (CI):

```bash
git tag v0.1.0
git push origin v0.1.0
# → GitHub Release with HelixOS-mac-x64.dmg
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

Set `HELIX_DATABASE_URL=sqlite:///$(pwd)/.data/helixos-dev.db` for persistent ELN/audit in browser dev (desktop sets a user-data SQLite URL automatically).

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
| Desktop troubleshooting | [docs/modules/desktop.md](docs/modules/desktop.md) |
| Public website | [docs/SITE.md](docs/SITE.md) |
| Session handover | [SESSION_HANDOVER.md](SESSION_HANDOVER.md) |

## MVP Modules

Implemented (UI + API where noted):

- [Auth & organizations](docs/modules/auth.md) — demo tokens + tenant scoping
- [ELN](docs/modules/eln.md) — workspaces (channels + share), projects, versioned experiments, samples/plates, datasets; **protocols library** (CRUD + import stubs)
- [Sequence metadata](docs/modules/molecular.md) — API metadata + client-side analyzer
- [AI copilot (SSE)](docs/modules/ai.md) — sessions, streaming runs, audit
- [MCP connectors](docs/modules/mcp.md) — BioPython local via desktop bridge
- [Audit trail](docs/modules/audit.md) — hash-chained events (memory / SQLite / Postgres)
- [Desktop shell](docs/modules/desktop.md) — Electron + sidecar + MCP bridge + packaged static UI

**Prototype only:** inventory tab (local state, no API). Planned: biobank, workflows — see [docs/OVERVIEW.md](docs/OVERVIEW.md).

## Agent Rules

Read [AGENTS.md](AGENTS.md) before changing code. Preserve typed schemas, API contracts, tests, and module documentation.
