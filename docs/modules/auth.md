# Authentication & Organizations

The auth module owns tenant boundaries, users, workspaces, RBAC roles, and permission checks. Every other domain depends on auth to resolve the **actor** and enforce `organization_id` scope.

**Related:** [eln.md](eln.md) · [audit.md](audit.md) · [SYSTEM_ARCHITECTURE.md](../../SYSTEM_ARCHITECTURE.md)

## Roles

- Admin
- PI
- Scientist
- Technician
- QA reviewer
- External collaborator

## Design Notes

- **Organizations** are tenant boundaries ([DOMAIN_GLOSSARY.md](../../DOMAIN_GLOSSARY.md)).
- **Workspaces** partition lab teams inside organizations (planned; not exposed in API yet).
- Permission checks must be explicit at service boundaries.
- SSO/OIDC should be integrated behind provider interfaces.

## API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/organizations` | Organizations visible to the bearer-token actor |

Full contract: [API_CONTRACTS.md](../../API_CONTRACTS.md).

## Local Development

| Token | Organizations |
| --- | --- |
| `org-demo-token` | `org_demo` |
| `demo-admin-token` | `org_demo`, `org_qc` |

The web app defaults to `org-demo-token` via `apps/web/.env.local`. Desktop injects the same through `window.helixDesktop` or `?helix_token=`.

## Downstream Consumers

- **ELN, molecular, AI, MCP, audit** — all call `organization_service.require_access(actor, organization_id)` before reads or writes.
- **Audit** — events store `actor_subject` from the resolved actor.

Production deployments should replace local token parsing with signed JWT validation while preserving the same actor contract. See [API_CONTRACTS.md](../../API_CONTRACTS.md#authentication).

## Audit And Permissions

The starter kit resolves local bearer tokens into an actor with explicit organization IDs. Service methods check this actor before returning tenant-scoped data; clients cannot widen access by passing arbitrary organization IDs.
