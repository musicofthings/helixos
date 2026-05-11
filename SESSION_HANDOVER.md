# Session Handover

Date: 2026-05-11

## Current State

HelixOS is a starter monorepo scaffold with a FastAPI backend, Next.js frontend, shared JSON Schemas, shared TypeScript types, module docs, examples, and MCP connector registry metadata.

This directory is not currently a Git worktree, so use filesystem inspection rather than `git diff` until the project is initialized or moved into a repository.

## Implemented This Session

- Added protected bearer-auth context for API routes.
- Added stable API error envelope handling.
- Added `auth` backend module:
  - `GET /api/v1/organizations`
  - local demo tokens mapped to visible organizations
  - service-level organization access checks
- Added `molecular` backend module:
  - `GET /api/v1/sequences/{sequence_id}`
  - seeded demo sequence metadata
  - tenant-scoped sequence retrieval
- Tightened existing routes:
  - experiments create/list require auth
  - experiment list is scoped to actor organizations
  - modules and MCP connectors require auth
- Updated API tests from 3 smoke tests to 9 behavior tests.
- Added `schemas/auth/organization.schema.json`.
- Added examples for organization and molecular sequence responses.
- Added shared TypeScript types for `Organization`, `Sequence`, and sequence feature contracts.
- Updated module docs and API contract docs.
- Replaced interactive `next lint` script with `eslint .` and added `apps/web/eslint.config.mjs`.
- Fixed frontend lint issues caused by unused imports and impure ID generation.
- Updated `README.md` with API, auth, endpoints, and checks.

## Local Auth Tokens

Use these only for local starter-kit development:

- `demo-admin-token`: access to `org_demo` and `org_qc`.
- `org-demo-token`: access to `org_demo`.

Example:

```bash
curl -H "Authorization: Bearer org-demo-token" \
  http://127.0.0.1:8000/api/v1/organizations
```

## Verification Commands

Backend:

```bash
cd /Users/theranosis_dx/projects/helixos/services/api
pytest
```

Frontend:

```bash
cd /Users/theranosis_dx/projects/helixos/apps/web
npm run lint
npm run typecheck
npm run build
```

Last known result: all commands passed.

## Known Follow-Ups

- Replace local demo bearer-token parsing with signed JWT validation through OIDC/JWKS.
- Add durable database models and repositories for auth, ELN, molecular records, and audit events.
- Wire the frontend to the API and shared `@helixos/types` contracts; current UI still uses local demo state.
- Add generated client/types workflow from JSON Schemas or OpenAPI.
- Add missing domain modules for inventory, biobank, workflows, and AI as real backend modules.
- Add schema validation tests for every JSON Schema example.
- Address `npm audit` report when Next provides a non-breaking fix for its transitive `postcss` advisory. Current audit suggests a breaking downgrade, so it was not applied.
- Remove local generated artifacts (`.DS_Store`, `.next`, `node_modules`, `__pycache__`, `.pytest_cache`) before publishing if this folder becomes a Git repository.

## Important Files

- `/Users/theranosis_dx/projects/helixos/API_CONTRACTS.md`
- `/Users/theranosis_dx/projects/helixos/services/api/helixos/auth/service.py`
- `/Users/theranosis_dx/projects/helixos/services/api/helixos/eln/service.py`
- `/Users/theranosis_dx/projects/helixos/services/api/helixos/molecular/service.py`
- `/Users/theranosis_dx/projects/helixos/services/api/tests/test_api.py`
- `/Users/theranosis_dx/projects/helixos/packages/types/src/index.ts`
- `/Users/theranosis_dx/projects/helixos/apps/web/eslint.config.mjs`
