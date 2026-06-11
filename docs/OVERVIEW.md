# HelixOS Platform Overview

HelixOS is an AI-native laboratory platform starter kit. It targets molecular biology labs, genomics diagnostics teams, and translational research groups that need ELN records, sequence tooling, inventory awareness, and agentic assistants in one workspace.

## What ships today (MVP)

| Capability | User surface | Backend | Persistence |
| --- | --- | --- | --- |
| Organizations & auth | Web / desktop | `helixos.auth` | In-memory demo actors |
| Experiment drafts (ELN) | Workspace → Experiments | `helixos.eln` | In-memory |
| Sequence metadata | Workspace → Sequences | `helixos.molecular` | In-memory demo data |
| Inventory UI | Workspace → Inventory | — | Client state only (no API yet) |
| AI lab copilot | Agent panel | `helixos.ai` | Sessions in memory; traces in audit store |
| MCP BioPython local | Connectors tab | `helixos.mcp` + desktop bridge | Job results ephemeral; audit persisted |
| Hash-chained audit | Sidebar trail + API | `helixos.audit` | Memory / SQLite / Postgres |
| Desktop shell | Electron app | `apps/desktop` + API sidecar | SQLite audit in dev/desktop |

## Planned domains (architecture scaffold)

These appear in [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and [DOMAIN_GLOSSARY.md](../DOMAIN_GLOSSARY.md) but do not yet have API routers:

- **inventory** — reagents, lots, expiry (UI prototype exists in the web workspace)
- **biobank** — samples, aliquots, chain of custody
- **workflows** — SOP state machines, approvals

New work should follow [agents/module_scaffold.md](../agents/module_scaffold.md) and register in [API_CONTRACTS.md](../API_CONTRACTS.md).

## Two ways to run the same workspace

| Mode | Command | Web | API | MCP |
| --- | --- | --- | --- | --- |
| Browser dev | `npm run dev:browser` | :3000 | :8000 | Not available (needs desktop bridge) |
| Desktop dev | `npm run dev:desktop` | :3000 | :8765 sidecar | :8766 bridge → stdio servers |

See [modules/desktop.md](modules/desktop.md) for how the sidecar, preload bridge, and query params wire the renderer to the local API.

## How information should flow in the product

1. **Tenant first** — Every regulated action is scoped to an [organization](modules/auth.md).
2. **Record work** — Scientists create [experiments](modules/eln.md) and inspect [sequences](modules/molecular.md).
3. **Assist safely** — The [AI copilot](modules/ai.md) reads workspace context and streams suggestions; tool calls are logged.
4. **Extend with tools** — [MCP connectors](modules/mcp.md) run local or remote scientific tools; desktop hosts stdio servers.
5. **Prove compliance** — The [audit module](modules/audit.md) appends hash-chained events per organization.

## Related documents

- Architecture and diagrams: [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md)
- Endpoint reference: [API_CONTRACTS.md](../API_CONTRACTS.md)
- Full doc index: [README.md](README.md)
