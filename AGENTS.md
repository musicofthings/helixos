# AGENTS.md

This repository is optimized for autonomous coding agents building a lab software platform. Preserve deterministic structure and typed contracts.

## Prime Directives

1. Read `SYSTEM_ARCHITECTURE.md`, `API_CONTRACTS.md`, `SCHEMA_GUIDE.md`, and `DOMAIN_GLOSSARY.md` before adding a module.
2. Add or update tests for every behavior change.
3. Keep modules isolated by domain: auth, eln, molecular, inventory, biobank, workflows, ai, mcp.
4. Prefer typed schemas and generated clients over ad hoc payloads.
5. Avoid hidden side effects. Make background jobs explicit.
6. Keep auditability as a first-class concern.

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

## Definition Of Done

- API contract documented
- Pydantic and TypeScript types updated
- Tests added
- Audit implications documented
- Example request/response included
- Permissions considered
