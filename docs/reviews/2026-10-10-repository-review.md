# Repository review — 2026-10-10

Reviewed commit: `48adf81` on `eln-versioned-hierarchy`, synchronized with its upstream. Fetch/prune and fast-forward pull succeeded; no incoming or outgoing commits. Existing untracked site asset directories were preserved.

Scope: architecture and API documentation; backend auth, ELN, audit, AI, molecular and MCP; shared types/client; web workspace and hooks; Electron lifecycle, sidecar, proxy and connector hosts; schemas/examples; setup, packaging, site and release workflows. This is a repository-wide review with targeted executable checks, not exhaustive verification of every runtime path.

## Findings

### P1 — Invited editors persist writes but receive 403

Location: `services/api/helixos/eln/service.py:396–411`, and equivalent subtree mutation methods; `services/api/helixos/audit/service.py:47`.

Workspace authorization accepts an editor grant from another organization. The domain write then completes, but `audit_service.record` checks organization membership and rejects that same actor. Reproduced: create an org_qc workspace as admin, invite org-demo-token as editor, accept, then create a project. The response is 403, but an admin list shows the persisted project. The audit event is absent and retrying can duplicate data.

Fix: authorize once using the workspace policy and pass the authorized actor identity to an internal audit interface. Do not relax organization-wide audit read permissions. Add editor create/update/delete tests across every subtree resource on memory and SQLite stores.

### P1 — Domain mutations and audit events commit separately

Location: `services/api/helixos/eln/service.py:403–404`; store transaction boundaries in `services/api/helixos/eln/sql_store.py`; separate append transaction in `services/api/helixos/audit/sql_store.py`.

An audit outage happens after the mutation is durable. Reproduced with a failing audit append: project creation returns 500 while the project remains visible. Deletions and signature transitions have the same structural risk. The client cannot determine whether a failed request changed regulated data.

Fix: use a shared SQL unit of work for domain mutations and audit appends, or atomically persist a durable audit outbox with the mutation and expose its delivery state. Add fault-injection tests for create, delete and signing; define equivalent failure behavior for the memory store.

### P1 — Invite acceptance bypasses use limits under concurrent requests

Location: `services/api/helixos/eln/sql_store.py:272–293`; activity check in `services/api/helixos/eln/service.py:353–375`.

Activity is checked before entering the acceptance transaction, and the counter is assigned from a detached snapshot. Two callers holding accepted_count=0 can both receive grants while both write accepted_count=1. Reproduced on SQLite by taking two snapshots of a max_uses=1 invite and executing the store acceptance operations: two grants persisted and the counter stayed at one. Revocation/expiry can also change between the service check and grant insertion.

Fix: recheck expiry, revocation and capacity in the acceptance transaction, using a conditional atomic increment or database locking. Create the grant in that transaction and translate conflicts into a stable API response. Add barrier-controlled acceptance/revocation tests.

### P1 — Concurrent transitions can unlock a signed version

Location: `services/api/helixos/eln/service.py:896–914`; `services/api/helixos/eln/sql_store.py:545–550`.

The service validates a detached version, while the store updates its status unconditionally. A request that read in_review before another request signs can later write draft over signed. Reproduced with the SQLite store using two updates from the same in_review snapshot: signed became draft.

Fix: compare-and-swap on the expected current status in the database transaction, and return 409 when the state changed. Apply equivalent locking in memory. Test simultaneous signing and rollback transitions through the API.

### P1 — PostgreSQL sample capacity is not serialized

Location: `services/api/helixos/eln/sql_store.py:553–598`.

Code-inspection finding; no live PostgreSQL test was run. Counting after an insert works with SQLite's serialized writes, but two PostgreSQL transactions can each insert the 96th sample and count only their own uncommitted row plus the 95 committed rows. Both can commit, resulting in 97 samples. Different or null well positions do not trigger the unique well constraint.

Fix: lock the parent experiment before allocating sample capacity, or atomically reserve capacity with a guarded counter. Add actual PostgreSQL concurrency coverage; SQLite passing does not establish PostgreSQL correctness.

### P2 — Agent validation happens after HTTP 200 headers

Location: `services/api/helixos/ai/router.py:28–43`; initial validation in `services/api/helixos/ai/service.py:83–84`.

Session lookup and tenant authorization occur when the streaming generator starts. Reproduced: a missing session returned HTTP 200 with a TestClient configured not to raise server exceptions. The intended 404/403 can no longer be represented by the normal error envelope once streaming starts.

Fix: resolve and authorize the session before constructing StreamingResponse. Add missing-session and cross-tenant run tests asserting HTTP status/envelope. Also move the successful done frame after the completion audit write, and handle cancellation explicitly so disconnected runs do not remain RUNNING.

### P2 — Malformed scientific tool arguments crash the connector

Location: `mcp/servers/biopython_local/server.py:67–70`.

The request boundary catches TypeError only. Reproduced with analyze_sequence(sequence=123): AttributeError from sequence.upper() terminated the process without a response. Incorrect params shapes can also escape the handler, interrupting unrelated pending jobs.

Fix: validate method, params and tool arguments using explicit typed schemas and return a per-request error. Keep a final exception boundary around each request. Test malformed input followed by a valid request in the same process. Separately, document DNA cleaning: the current analyzer silently discards ambiguity symbols and non-ACGT characters.

### P2 — Failed process spawning can terminate Electron

Location: `apps/desktop/src/main/mcp/host-manager.ts:34–94`; `apps/desktop/src/main/sidecar.ts:46–94`.

Code-inspection finding. Spawned children have exit handlers but no error handlers. Missing Python/binary or an execution-permission failure emits an unhandled error, rather than a recoverable startup failure. Connector start also resolves before spawn success is established.

Fix: handle spawn errors, reject startup, clear state and pending requests, and show a recoverable sidecar/connector error. In both stop methods, use exit state rather than child.killed for SIGKILL escalation: killed means a signal was sent, not that the process exited. Add startup failure and SIGTERM-resistant child tests.

## Improvements in priority order

1. Fix authorization/audit consistency and atomic lifecycle changes before expanding regulated features. Add the targeted regressions above.
2. Add pull-request CI running API tests against memory, SQLite and PostgreSQL; web lint/typecheck/build; desktop typecheck/build; connector tests; and schema/example validation. Existing workflows cover site deployment and desktop release, without a general PR validation workflow.
3. Introduce versioned migrations. Startup's additive-column loop does not migrate constraints, indexes, non-nullable columns or data; enable and test SQLite foreign-key enforcement as well.
4. Make contracts mechanically verifiable or generated. JSON schemas, Pydantic models and TypeScript types are maintained separately. Most new ELN entities have no corresponding example file. Update stale OVERVIEW/auth/audit documentation: ELN now has SQL persistence, workspace endpoints and many audited actions beyond AI/MCP.
5. Strengthen release validation: require at least one usable bundled Python execution path, validate runtime imports in the packaged artifact, and smoke-test sidecar plus connector on a clean machine. Resource preparation currently treats Python build/bootstrap failures as optional. Align the updater feed with the actual release host and distribute the archives/metadata needed for updates; the builder currently points at an example domain.
6. Add web/client tests for collaborator roles, failed mutations, cache invalidation, experiment switching and truncated SSE streams. Give streaming requests AbortSignal support and release/cancel the reader in finally. Bound in-memory AI session/run retention and avoid retaining every streamed token indefinitely.
7. Add pagination for hierarchy listings and structured logging with request/job IDs. Validate dataset sequence references and scientific payloads at the service boundary as molecular functionality becomes durable.

## Validation

- API: all 84 tests passed; two deprecation warnings.
- Web: typecheck, lint and production build passed.
- Desktop: typecheck and Electron Vite build passed; build emitted 'renderer config is missing' but generated main/preload bundles successfully.
- Site: build passed.
- git diff --check passed before this report was added.
- Targeted checks reproduced editor 403-after-write, audit 500-after-write, invite counter loss/use-limit bypass, signed-status overwrite, invalid-session HTTP 200, and connector crash.

Not exercised: live PostgreSQL, packaged Electron interaction, clean-machine installation, external model providers, updater/download flow, browser end-to-end tests, or dependency vulnerability databases. Passing builds do not verify those surfaces.

No application code was modified, committed or pushed during this review.
