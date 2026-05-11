# Module Scaffold Playbook

Use this checklist when adding a HelixOS domain module.

1. Create `services/api/helixos/<module>/`.
2. Add `schemas.py`, `service.py`, `router.py`, and `models.py` as needed.
3. Add JSON Schemas under `schemas/<module>/`.
4. Add docs under `docs/modules/<module>.md`.
5. Register the router in `services/api/helixos/main.py`.
6. Add tests under the module or `tests/`.
7. Update `API_CONTRACTS.md`.
