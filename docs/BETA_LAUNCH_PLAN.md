# Beta Launch Plan

_Assessed 2026-10-13 on branch `eln-versioned-hierarchy` (`27718df`). Based on code and doc inspection plus a full API test run; items marked **unverified** were not exercised._

## Where we are

**Solid foundations** (verified: 171 API tests pass, 4 Postgres tests skip locally and run in CI):

- ELN hierarchy with workspaces, projects, versioned experiments, samples, datasets, sharing and invites.
- Mutations and audit events commit atomically on SQL stores. All five P1s from the [2026-10-10 review](reviews/2026-10-10-repository-review.md) are fixed and have regression tests, including Postgres concurrency (capacity, invite limits, signed-version CAS, concurrent migrations).
- Alembic migrations, SQL pagination, structured JSON logs with request IDs, hash-chained audit.
- CI covers API on memory/SQLite/Postgres, generated-type drift, smoke tests and agent evals, connector, web (typecheck, lint, test, build) and desktop.

**Not beta-ready.** The product is a strong local/dev stack with no hosted deployment, no real identity, and some modules that are demos.

## P0 — Blockers (nothing ships without these)

| # | Item | Evidence | Size |
| --- | --- | --- | --- |
| 1 | ✅ **Real authentication** (done 2026-10-13, see [modules/auth.md](modules/auth.md)). OIDC/JWKS verification, users and memberships in the DB, web sign-in/out, demo tokens unreachable in production. Verified with real Postgres and in a browser against a mock provider; **not yet against a real provider** (Auth0/Clerk/Google). | `auth/oidc.py`, `auth/service.py`, `apps/web/lib/auth.ts` | L |
| 2 | ✅ **Role-based authorization** (done 2026-10-13). Six org roles enforced in the ELN; admins invite, re-role and remove members from the Members screen. Not done: email delivery of invites, self-serve org creation (operator CLI for the beta). | `auth/roles.py`, `auth/members.py` | M |
| 3 | 🟡 **Hosted deployment** (code done 2026-10-13, **not applied to a live project**). Both images build and run together against Postgres (verified); Terraform for Cloud Run + Cloud SQL (PITR) + Secret Manager + Artifact Registry + GitHub federation validates; staging auto-deploys after CI, production is approval-gated, releases verify at zero traffic, rollback is one input ([DEPLOYMENT.md](DEPLOYMENT.md)). Open: a GCP project per environment, the first `terraform apply` and pipeline run, custom domain/TLS, alerting. | `deploy/terraform`, `.github/workflows/deploy.yml`, both Dockerfiles | L |
| 4 | ✅ **Production config and CORS** (done 2026-10-13, see [DEPLOYMENT.md](DEPLOYMENT.md)). `HELIX_ENV` posture, startup validation, explicit `ALLOWED_ORIGINS`, docs off in prod, relative `/api` plus Next proxy, no demo token in production bundles. Remaining: the OIDC verifier itself (item 1). | `config.py`, `main.py`, `next.config.ts` | S |
| 5 | **Rate limiting and abuse controls.** Per-actor/org limits, request-size caps, and a spend cap on AI provider calls (openai/vertex). | No limiter anywhere in `helixos/` | M |
| 6 | 🟡 **Backups and recovery.** Daily backups (14 kept) + 7-day point-in-time recovery are configured in Terraform, and the restore drill and audit-chain verification are written down ([DEPLOYMENT.md](DEPLOYMENT.md#backups-and-recovery)). **Not done until someone has run the drill on a real instance.** | `deploy/terraform/main.tf` | M |
| 7 | **Legal and data posture.** Terms, privacy policy, "research use only, not for clinical decisions" notice, decision on what data classes beta may hold (human genomic data triggers DPDP/HIPAA-class obligations). | None in repo | M (mostly non-code) |

## P1 — Required for a credible beta

**Reliability and ops**
- ✅ `/ready` (database reachable, migrations at head), separate from `/health`; used by Cloud Run's startup probe and the deploy smoke test. Still open: metrics, error tracking, uptime check and alerting, status page.
- Load test the list/hierarchy endpoints and SSE runs against Postgres at beta scale; set instance sizing.
- Dependency and secret scanning in CI (`pip-audit`, `npm audit`, Dependabot, secret scan); pin Python to one version (local venv is 3.11, CI is 3.12).
- Browser end-to-end tests (Playwright) for the core path: sign in, create workspace, project, experiment, share, sign version. No e2e exists today.

**Persistence gaps that would lose or fake user data**
- AI sessions and runs live in memory (bounded, evicted); a restart drops history. Persist or label as ephemeral in the UI.
- Sequence metadata is in-memory demo data; persist it per org.
- MCP job results are ephemeral. Fine if documented; audit is already persisted.
- Inventory is client-state only. Either build the API (see P2) or hide the tab for beta.

**Product completeness**
- ✅ Org/user management UI (Members screen). Still open: email delivery for invites (invitees must sign in with the invited address).
- Experiment data export (PDF/JSON) so beta users can leave and trust the platform with records.
- File and attachment storage (S3-compatible). Architecture says "not implemented in MVP"; ELN without attachments will be the first complaint.
- Finish protocols library (CRUD works, import is stubbed).
- Onboarding: first-run empty states, sample workspace, in-app help, known-limitations page.

**Desktop (only if desktop is in beta scope)**
- Apple Developer ID signing and notarization (`CSC_IDENTITY_AUTO_DISCOVERY: "false"` today; release notes say unsigned).
- Release currently ships `HelixOS-mac-x64.dmg`; confirm Apple Silicon story (**unverified**).
- Updater feed publish silently skips when R2 secrets are missing; make it fail the release instead.
- Clean-machine smoke test of the packaged app (sidecar and connector start, bundled Python imports).
- Browser mode has no MCP connectors; set that expectation in the beta pitch.

## P2 — Post-beta / defer

- Inventory backend (reagents, lots, expiry), biobank, workflows/SOP approvals: still scaffold only. Keep out of beta scope and say so.
- Full-text search across notebooks, notifications, real-time collaboration.
- Windows/Linux desktop builds.
- 21 CFR Part 11-style e-signature claims: versions have signing states, but do not market compliance until reviewed.

## Housekeeping to do now

- `SESSION_HANDOVER.md` is a blank template and says P1s are blocked; they are not. Regenerate it.
- Stale docs: README "Current Status (July 2026)", `auth.md` says workspaces are "planned; not exposed", OVERVIEW auth row.
- Untracked: `api_docs.md` (scratch?), `apps/site/assets/3d/`, `apps/site/assets/images/`, `session_handover.md.lock`. Commit, ignore, or delete.
- Merge `eln-versioned-hierarchy` to `main` before building deploy work on top.

## Suggested sequencing

1. **Foundation (do first, unblocks everything):** P0-4 config hardening, P0-3 Dockerfile and staging environment, merge to main, housekeeping.
2. **Identity:** P0-1 and P0-2 (pick IdP first), web sign-in, org admin UI.
3. **Safety net:** P0-5, P0-6, readiness/metrics/alerts, vulnerability scanning, Playwright core path.
4. **Beta content:** persistence gaps, export, attachments, onboarding.
5. **Gate:** load test, restore drill, legal sign-off, closed beta with a small named cohort, then widen.

## Decisions needed from you

| Decision | Recommendation |
| --- | --- |
| Beta surface: browser, desktop, or both | Browser-first. It is where hosted auth and Postgres live; desktop adds signing and notarization work and MCP only matters there. |
| Identity provider | Managed OIDC (Auth0, Clerk, Google Identity Platform) behind the existing actor contract; avoid building password auth. |
| Hosting | Cloud Run in `asia-south1` plus managed Postgres, matching workspace conventions. Confirm that is acceptable for beta data residency. |
| Data allowed in beta | Non-clinical, de-identified research data only, stated in the terms. |
| Cohort size and access | Invite-only, 5–15 labs, so rate limits and support load stay manageable. |

## Exit criteria for opening the beta

- Production boots only with real auth, Postgres, and explicit CORS origins.
- A restore from backup has been performed and the audit chain verified afterward.
- Core-path e2e test green in CI against a staging deploy.
- No demo tokens or API keys in any shipped bundle.
- Terms, privacy policy, and a known-limitations page are live.
- Alerting reaches a human, and someone owns support during the beta.
