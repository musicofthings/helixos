# Session Handover
_Generated: 2026-06-07_
_Branch: main_
_Trigger: user request (end of session)_

---

## Active Task

**What we're building/fixing:**
HelixOS — AI-native lab platform moving from starter kit toward production. Local dev is fully functional (browser + desktop). Documentation is connected. Data flows between UI, API, and audit store are wired.

**Phase:** Post-MVP hardening — production readiness not started
**Next action:** Commit uncommitted work, then pick first production item from Remaining Work below (recommend: Postgres persistence for ELN + audit, or JWT/OIDC auth)

---

## Completed This Session

- [x] Connected documentation hub (`docs/README.md`, `docs/OVERVIEW.md`, cross-linked module docs, architecture flow diagrams)
- [x] Root dev orchestration (`package.json`, `scripts/setup-dev.sh`, `dev-api.sh`, `dev-desktop.sh`, `.env.example`)
- [x] Hash-chained audit storage (SQLite/Postgres) with verify endpoint
- [x] Desktop shell fixes (CJS build, hydration, `window is not defined`, sidecar startup)
- [x] Data flow fixes across web ↔ API ↔ audit:
  - Agent session: one session per org (no refetch-create bug)
  - Audit sidebar: invalidates after regulated actions, merged API + local activity
  - ELN: `PATCH /api/v1/experiments/{id}` for status transitions + audit events
  - Sequences: demo metadata from API (`seq_demo_reporter`)
  - MCP: BioPython enabled by default; desktop-only guard; no fake connector success
  - Organization picker for multi-org tokens
- [x] API client: `getSequence()`, `updateExperimentStatus()`
- [x] Tests: 26 passing (3 new ELN/audit tests)

---

## In Progress (Exact Resume Point)

**Branch:** `main`
**Last commit:** `7802bbf Implement HelixOS starter platform`
**Working tree:** Large uncommitted diff — all session work is local only, not committed

**Next immediate action:**
1. Review `git status` and commit session work (or split into logical commits)
2. Run `npm run dev:browser` or `npm run dev:desktop` to verify stack still starts
3. Pick production milestone from Remaining Work

---

## Remaining Work (Production Path)

### P0 — Foundation
1. **Commit current work** — significant uncommitted changes on `main`
2. **Postgres persistence** — ELN experiments currently in-memory; wire SQLAlchemy repositories
3. **Auth for production** — replace demo bearer tokens with JWT/OIDC validation
4. **Environment config** — production `.env` templates, secrets management, CORS lockdown

### P1 — Core product
5. **Inventory module** — scaffold `helixos/inventory` per AGENTS.md; replace local UI prototype
6. **Audit verify in UI** — expose `GET /api/v1/audit/verify` in workspace sidebar
7. **ELN persistence** — experiments survive API restart; add experiment edit/blocks API
8. **Sequence storage** — full sequence content (not just metadata); import FASTA/GenBank

### P2 — Desktop & release
9. **Desktop packaging CI** — `npm run pack` with embedded Python on all platforms
10. **Auto-update URL** — replace placeholder `releases.helixos.example`
11. **Code signing / notarization** — macOS/Windows release pipeline
12. **Static web export** — packaged desktop loads bundled web, not Next dev server

### P3 — Planned domains
13. **Biobank module** — samples, aliquots, chain of custody
14. **Workflows module** — SOP state machines, approvals (replace local diagnostic workflow UI)
15. **Additional MCP connectors** — PubMed, BLAST, etc. (registry metadata exists today)

---

## Architecture Decisions Made

| Decision | Rationale | Date |
| --- | --- | --- |
| Doc hub at `docs/README.md` | Single reading order; modules cross-link | 2026-06-07 |
| Agent session via `useEffect`, not `useQuery` | POST-as-fetch created duplicate sessions + audit noise | 2026-06-07 |
| ELN status via PATCH + audit | Replaces local-only UI overrides; production-ready pattern | 2026-06-07 |
| BioPython `enabled_by_default: true` | Stdio connector is primary desktop use case | 2026-06-07 |
| Audit invalidation after regulated actions | Sidebar stayed stale without explicit refetch | 2026-06-07 |
| Desktop CJS build (`.cjs`) | ESM broke `electron-updater` at launch | 2026-06-07 |
| SQLite audit for local/desktop dev | Postgres for server; memory for CI | 2026-06-07 |

---

## Commands to Resume

```bash
cd ~/projects/helixos
git status                    # review uncommitted work
npm run setup                 # if fresh machine
npm run dev:browser           # browser: API :8000 + web :3000
npm run dev:desktop           # desktop: sidecar :8765 + MCP :8766
npm run test:api              # 26 pytest tests

# Audit with SQLite (browser dev):
export HELIX_DATABASE_URL=sqlite:///$(pwd)/.data/helixos-dev.db
npm run dev:api
```

Demo tokens: `org-demo-token` (org_demo), `demo-admin-token` (org_demo + org_qc)

---

## Files Modified This Session

| Area | Key files |
| --- | --- |
| Documentation | `README.md`, `SYSTEM_ARCHITECTURE.md`, `docs/README.md`, `docs/OVERVIEW.md`, `docs/modules/*.md`, `AGENTS.md`, `API_CONTRACTS.md` |
| Web UI | `apps/web/components/workspace-app.tsx`, `apps/web/hooks/use-helix-api.ts`, `apps/web/components/agent/agent-panel.tsx`, `apps/web/lib/*` |
| API client | `packages/api-client/src/index.ts`, `packages/types/src/index.ts` |
| Backend ELN | `services/api/helixos/eln/{router,service,schemas}.py` |
| Backend audit/AI/MCP | `services/api/helixos/audit/`, `services/api/helixos/ai/`, `services/api/helixos/mcp/` |
| Desktop | `apps/desktop/` (Electron shell, sidecar, MCP bridge) |
| Dev scripts | `package.json`, `scripts/dev-*.sh`, `.env.example` |
| Tests | `services/api/tests/test_api.py` (+ audit, hash_chain, ai_providers) |

---

## Git Context

```
Branch  : main
Commit  : 7802bbf Implement HelixOS starter platform
Status  : dirty (extensive uncommitted changes — see git status)
```

Recent commits:
```
7802bbf Implement HelixOS starter platform
```

---

## Critical Rules

- Never commit secrets (`.env`, credentials, API keys)
- Read [AGENTS.md](AGENTS.md) and [docs/README.md](docs/README.md) before adding modules
- Update tests + API_CONTRACTS.md for every behavior change
- Inventory/workflow UI is prototype-only until backend modules exist

---

## Verification Checklist (Last Known Good)

- [x] `npm run test:api` — 26 tests pass
- [x] `npx tsc --noEmit` in `apps/web` — clean
- [x] Browser dev: ELN create/list/status, sequences metadata, agent SSE, audit sidebar
- [x] Desktop dev: sidecar :8765, MCP bridge :8766, BioPython connector jobs
- [ ] Production deploy — not attempted
- [ ] `npm run pack` full desktop release — not verified end-to-end

---

_Auto-updated at session end. Read this at the start of the next session._
