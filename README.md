# HelixOS

AI-native Laboratory Management & Molecular Biology Platform Starter Kit.

HelixOS is a modular starter kit for molecular biology labs, genomics diagnostics teams, academic groups, biotech startups, and translational research organizations. It combines ELN, LIMS-lite workflows, molecular biology design tools, biobank/inventory management, AI copilots, and an MCP connector framework.

## Repository Layout

```txt
apps/        User-facing applications, starting with the Next.js web app.
services/    Backend services, starting with the FastAPI API.
packages/    Shared TypeScript packages.
schemas/     Canonical JSON Schemas and cross-language contracts.
agents/      Agent playbooks and task templates.
prompts/     System and product prompts for AI features.
mcp/         MCP connector manifests and registry.
docs/        Architecture, contracts, glossary, and module notes.
examples/    Seed examples and demo data.
tests/       Cross-cutting tests.
```

## MVP Modules

- Authentication and organizations
- Electronic Lab Notebook
- Molecular biology workspace
- Inventory and reagents
- AI copilot layer
- MCP connector framework

## Quick Start

### API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e services/api[dev]
cd services/api
pytest
uvicorn helixos.main:app --reload
```

The API serves public health checks at `/health` and protected REST endpoints under `/api/v1`.

Local starter bearer tokens:

- `demo-admin-token`: access to `org_demo` and `org_qc`.
- `org-demo-token`: access to `org_demo`.

Example:

```bash
curl -H "Authorization: Bearer org-demo-token" \
  http://127.0.0.1:8000/api/v1/organizations
```

Implemented API endpoints:

- `GET /health`
- `GET /api/v1/modules`
- `GET /api/v1/organizations`
- `POST /api/v1/experiments`
- `GET /api/v1/experiments`
- `GET /api/v1/sequences/{sequence_id}`
- `GET /api/v1/mcp/connectors`

### Web

```bash
cd apps/web
npm install
npm run dev
```

Useful web checks:

```bash
npm run lint
npm run typecheck
npm run build
```

## Contracts And Schemas

- API behavior is documented in [API_CONTRACTS.md](API_CONTRACTS.md).
- Shared JSON Schemas live in `schemas/`.
- Example payloads live in `examples/`.
- Shared TypeScript contracts live in `packages/types/src/index.ts`.
- Module notes live in `docs/modules/`.

## Agent Rules

Read [AGENTS.md](AGENTS.md) before changing code. All generated modules must preserve typed schemas, API contracts, tests, and module documentation.
