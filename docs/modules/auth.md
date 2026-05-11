# Authentication & Organizations

The auth module owns tenant boundaries, users, workspaces, RBAC roles, and permission checks.

## Roles

- Admin
- PI
- Scientist
- Technician
- QA reviewer
- External collaborator

## Design Notes

- Organizations are tenant boundaries.
- Workspaces partition lab teams inside organizations.
- Permission checks must be explicit at service boundaries.
- SSO/OIDC should be integrated behind provider interfaces.

## API Surface

- `GET /api/v1/organizations` returns only organizations visible to the bearer-token actor.

## Audit And Permissions

The starter kit resolves local bearer tokens into an actor with explicit organization IDs. Service methods check this actor before returning tenant-scoped data. Production deployments should replace local token parsing with signed JWT validation while preserving the same actor contract at service boundaries.
