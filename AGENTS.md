# AGENTS.md

This repository is optimized for autonomous coding agents building a lab software platform. Preserve deterministic structure and typed contracts.

## Documentation Reading Order

Start at [docs/README.md](docs/README.md), then read as needed:

1. [docs/OVERVIEW.md](docs/OVERVIEW.md) — MVP scope and run modes
2. [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) — components and request flows
3. [API_CONTRACTS.md](API_CONTRACTS.md) — REST endpoints
4. [SCHEMA_GUIDE.md](SCHEMA_GUIDE.md) — JSON Schema rules
5. [DOMAIN_GLOSSARY.md](DOMAIN_GLOSSARY.md) — lab vocabulary
6. [docs/modules/](docs/modules/) — domain deep-dives for the module you touch

## Prime Directives

1. Read the documents above before adding a module.
2. Add or update tests for every behavior change.
3. Keep modules isolated by domain: auth, eln, molecular, inventory, biobank, workflows, ai, mcp, audit.
4. Prefer typed schemas and generated clients over ad hoc payloads.
5. Avoid hidden side effects. Make background jobs explicit.
6. Keep auditability as a first-class concern — regulated actions go through [docs/modules/audit.md](docs/modules/audit.md).

## Required Pattern For New Modules

```txt
services/api/helixos/<module>/
  router.py
  schemas.py
  service.py
  models.py
  tests/
docs/modules/<module>.md
schemas/<module>/*.schema.json
```

Register the router in `services/api/helixos/main.py`. Add the module to [docs/README.md](docs/README.md) and [API_CONTRACTS.md](API_CONTRACTS.md).

## Definition Of Done

- API contract documented in [API_CONTRACTS.md](API_CONTRACTS.md)
- Module doc in `docs/modules/` with **Related** links to dependent modules
- Pydantic and TypeScript types updated
- Tests added
- Audit implications documented (if regulated)
- Example request/response included
- Permissions considered via [auth](docs/modules/auth.md)

Scaffold checklist: [agents/module_scaffold.md](agents/module_scaffold.md).
