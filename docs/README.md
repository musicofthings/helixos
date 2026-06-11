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
| [modules/desktop.md](modules/desktop.md) | Electron shell, API sidecar, MCP bridge, packaging |
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
