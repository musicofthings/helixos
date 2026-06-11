# Module Scaffold Playbook

Use this checklist when adding a HelixOS domain module. Read [docs/README.md](../docs/README.md) and [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) first.

1. Create `services/api/helixos/<module>/` with `schemas.py`, `service.py`, `router.py`, and `models.py` as needed.
2. Add JSON Schemas under `schemas/<module>/` per [SCHEMA_GUIDE.md](../SCHEMA_GUIDE.md).
3. Add `docs/modules/<module>.md` with **Related** links to auth and any dependencies.
4. Register the router in `services/api/helixos/main.py`.
5. Add tests under the module or `tests/`.
6. Update [API_CONTRACTS.md](../API_CONTRACTS.md) and [docs/modules/README.md](../docs/modules/README.md).
7. Document audit implications in the module doc if the domain performs regulated actions — see [docs/modules/audit.md](../docs/modules/audit.md).
8. Enforce tenant scope via [auth](../docs/modules/auth.md) (`require_access`) on every service entry point.

Definition of done: [AGENTS.md](../AGENTS.md).
