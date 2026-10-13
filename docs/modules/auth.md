# Authentication & Organizations

The auth module owns tenant boundaries, users, memberships, roles, and permission checks. Every other domain depends on it to resolve the **actor** and enforce `organization_id` scope.

**Related:** [eln.md](eln.md) · [audit.md](audit.md) · [../DEPLOYMENT.md](../DEPLOYMENT.md) · [SYSTEM_ARCHITECTURE.md](../../SYSTEM_ARCHITECTURE.md)

## How sign-in works

1. The web app signs the user in with any OpenID Connect provider (authorization code + PKCE) and sends the resulting token as `Authorization: Bearer …`.
2. The API verifies it: signature against the provider's JWKS, `iss`, `aud`, `exp`. Only asymmetric algorithms from an allow-list are accepted (`none` and HMAC are rejected). Keys are cached; an unknown `kid` triggers at most one refetch per 30 seconds, and a provider outage never signs users out (`503 auth_unavailable`, cached keys keep working).
3. The user is found or created by `(issuer, sub)`. Pending invites for their **verified** email are claimed, and their memberships become the actor's organizations and roles.

HelixOS stores its own user id (`usr_…`); that id, not the provider's `sub`, appears in audit events and workspace shares. Email is stored and used for matching only when the provider says `email_verified: true`, so an unverified address can neither claim an invite nor inherit an email-addressed share.

### Provider requirements

| Need | Setting |
| --- | --- |
| Issuer URL | `HELIX_OIDC_ISSUER` (https; `http://localhost…` allowed for dev). Must equal the token's `iss` exactly, including any trailing slash. |
| Audience | `HELIX_OIDC_AUDIENCE`: the API identifier (or client id, if you send ID tokens) the token's `aud` carries |
| Keys | Discovered from `{issuer}/.well-known/openid-configuration`, or set `HELIX_OIDC_JWKS_URL` |
| Claims | `sub`; plus `email` and `email_verified` (names configurable via `HELIX_OIDC_EMAIL_CLAIM` / `HELIX_OIDC_NAME_CLAIM`). Many providers need a rule/action/template to put `email` in an *access* token. |
| Algorithms | `HELIX_OIDC_ALGORITHMS` (default `RS256,ES256`) |
| Web app | `NEXT_PUBLIC_OIDC_AUTHORITY`, `NEXT_PUBLIC_OIDC_CLIENT_ID`; optionally `_AUDIENCE` (extra authorize parameter for providers like Auth0), `_SCOPE`, `_TOKEN_TYPE=id_token` (e.g. Google). Callback URL: the site root. |

Enable refresh tokens and a token lifetime of an hour or more (add `offline_access` to `NEXT_PUBLIC_OIDC_SCOPE` where the provider supports it); otherwise the browser is sent back through sign-in when the token expires.

## Roles

A user holds one role **per organization**.

| Role | Org's own workspaces | Sign off experiments | Manage members |
| --- | --- | --- | --- |
| `admin` | owner | yes | yes |
| `pi` | owner | yes | |
| `scientist` | owner | yes | |
| `technician` | editor (no sharing/deleting workspaces) | | |
| `qa_reviewer` | read-only | yes | |
| `external_collaborator` | none; sees only workspaces explicitly shared with them | | |

Workspace sharing (viewer/editor grants by email, user id or invite link) works as before and applies on top of the role; the strongest of the two wins. An organization must always keep at least one admin.

## Creating organizations (beta: operator-provisioned)

There is no self-serve sign-up. An operator creates the organization and its first admin; that person becomes admin on their first verified sign-in and invites everyone else from **Members**.

```bash
python -m helixos.auth.admin create-org --id org_acme --name "Acme Labs" --admin-email pi@acme.example
python -m helixos.auth.admin add-member --org org_acme --email a@acme.example --role scientist
python -m helixos.auth.admin list-orgs
python -m helixos.auth.admin disable-user --user usr_…   # blocks sign-in (403 account_disabled)
```

The CLI applies migrations, uses `HELIX_DATABASE_URL`, and writes audit events as `operator-cli`. In the container: `docker run --rm -e HELIX_DATABASE_URL=… helixos-api python -m helixos.auth.admin …`.

## API Surface

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/v1/organizations` | Organizations the caller belongs to, with their `role` |
| `GET` | `/api/v1/organizations/{id}/members` | Members and pending invites |
| `POST` | `/api/v1/organizations/{id}/members` | Add a known user or invite an email (admin) |
| `PATCH` / `DELETE` | `/api/v1/organizations/{id}/members/{user_id}` | Change role / remove (admin) |
| `DELETE` | `/api/v1/organizations/{id}/member-invites/{invite_id}` | Revoke an invite (admin) |

Full contract: [API_CONTRACTS.md](../../API_CONTRACTS.md). Membership changes are audited with ids and roles only; the audit log is append-only and hash-chained, so no email addresses are written into it.

## Local development

| Mode | How |
| --- | --- |
| Demo tokens (default) | `org-demo-token` (scientist in `org_demo`), `demo-admin-token` (admin in `org_demo` and `org_qc`). The web app defaults to `org-demo-token`; desktop injects the same. |
| Real sign-in flow | `bash scripts/dev-oidc.sh mock`, then `api`, then `web` (three terminals). A mock provider on :9100 lets you pick a user; `admin@acme.test` is admin of `org_acme`. |

Demo tokens and `HELIX_ALLOW_UNVERIFIED_JWT` are gated by `HELIX_ENV`: opt-in in staging (`HELIX_ENABLE_DEMO_TOKENS=1`), never in production, and unsigned JWTs are refused when hosted.

## Not yet built

- Self-serve organization creation and email delivery of invites (invitees simply sign in with the invited address).
- Per-request caching of memberships (each request reads them, so removals take effect immediately but cost a query).
- Audit-read restrictions by role; every member can read their organization's audit trail.
- SCIM/SSO group mapping, MFA policy (delegated to the identity provider).
