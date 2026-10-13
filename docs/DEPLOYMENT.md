# Deployment

How the hosted API is configured and packaged. Desktop and local dev are unaffected: with `HELIX_ENV` unset the API runs in `development` posture exactly as before.

## Environments

`HELIX_ENV` selects the posture. An unknown value (including `prod`) stops startup rather than silently running as development.

| Setting | `development` (default) | `staging` | `production` |
| --- | --- | --- | --- |
| Demo bearer tokens | on | off unless `HELIX_ENABLE_DEMO_TOKENS=1` | never (flag is a startup error) |
| Unsigned JWTs (`HELIX_ALLOW_UNVERIFIED_JWT`) | opt-in | ignored; startup error if set | ignored; startup error if set |
| CORS | any `localhost`/`127.0.0.1` port + `ALLOWED_ORIGINS` | `ALLOWED_ORIGINS` only, required | `ALLOWED_ORIGINS` only, required, https only |
| Identity provider (OIDC) | optional | optional | **required** |
| Database | memory / SQLite / Postgres | SQLite or Postgres (memory refused) | Postgres only |
| AI provider | any (stub default) | any (warns on stub) | `openai` or `vertex` with credentials; stub refused |
| `/docs`, `/openapi.json` | on | on | off (`HELIX_ENABLE_DOCS=1` to override) |

All violations are reported together in one error. `*` is rejected as an origin in every environment.

**Authentication** is OIDC (`HELIX_OIDC_ISSUER`, `HELIX_OIDC_AUDIENCE`); production refuses to start without it and never accepts demo tokens. Staging can use either: real sign-in, or demo tokens with `HELIX_ENABLE_DEMO_TOKENS=1`. Details, provider requirements and creating the first organization: [modules/auth.md](modules/auth.md).

## API image

Build from the repository root. The API reads `mcp/registry.json` and `prompts/` relative to the repo layout, so the image mirrors it and runs from source rather than a site-packages install.

```bash
docker build -f services/api/Dockerfile -t helixos-api .
```

Run it (migrations apply automatically at startup):

```bash
docker run --rm -p 8000:8000 \
  -e HELIX_ENV=production \
  -e HELIX_DATABASE_URL='postgresql+psycopg://USER:PASS@HOST:5432/DB' \
  -e ALLOWED_ORIGINS=https://app.example.com \
  -e HELIX_OIDC_ISSUER=https://idp.example.com/ -e HELIX_OIDC_AUDIENCE=helixos-api \
  -e HELIX_AI_PROVIDER=openai -e HELIX_OPENAI_API_KEY=... \
  helixos-api

# first organization and its admin (applies migrations, idempotent per id)
docker run --rm -e HELIX_DATABASE_URL='postgresql+psycopg://USER:PASS@HOST:5432/DB' \
  helixos-api python -m helixos.auth.admin create-org --id org_acme --name "Acme Labs" \
  --admin-email pi@acme.example
```

Or try the image against local Postgres in staging posture:

```bash
docker compose --profile app up --build api
```

Notes:

- The container listens on `$PORT` (default 8000), runs as a non-root user, and has a `/health` healthcheck.
- **Run exactly one instance with one worker.** AI sessions and runs live in process memory until persisted; a second instance cannot see the first's sessions.
- Set `FORWARDED_ALLOW_IPS` when behind a proxy (`*` on Cloud Run) so `X-Forwarded-*` headers are honored.
- Streaming (`/api/v1/ai/runs`) is long-lived: raise the platform request timeout accordingly.
- `.dockerignore` is an allowlist, so `.env` files and local databases cannot enter the build context.

## Web app

The browser calls `/api/...` on its own origin and Next forwards it to the API, so no API origin is baked into the bundle and CORS is not exercised.

- `HELIX_API_PROXY_TARGET` (default `http://127.0.0.1:8000`) sets the forward target. It is baked in at `next build`, so set it when building.
- `NEXT_PUBLIC_API_URL` is only for bypassing the proxy; the target origin must then be in `ALLOWED_ORIGINS`.
- Production bundles do not default to the demo token. `NEXT_PUBLIC_*` values are public, so a staging build that sets `NEXT_PUBLIC_API_TOKEN` exposes that token to every visitor until real sign-in exists.
- The packaged desktop app (static export) is unchanged: it gets its API URL and token from the Electron bridge.

### Web image

```bash
docker build -f apps/web/Dockerfile -t helixos-web \
  --build-arg HELIX_API_PROXY_TARGET=https://api.example.com \
  --build-arg NEXT_PUBLIC_OIDC_AUTHORITY=https://idp.example.com/ \
  --build-arg NEXT_PUBLIC_OIDC_CLIENT_ID=... .
```

Next's standalone server, non-root, listening on `$PORT` (default 8080). Public settings are compiled in, so **build one web image per environment** (the API image is environment-agnostic and can be promoted unchanged). Never pass a secret as a build argument. `.dockerignore` excludes every `.env*` file so a local `.env.local` cannot leak its dev token into a bundle.

The API marks its event streams `Cache-Control: no-transform`. Without it Next's proxy gzips the stream and delivers the whole agent run in one burst at the end; keep that header if you ever change the streaming response.

## Hosted deployment (GCP Cloud Run, `asia-south1`)

Infrastructure is Terraform in [`deploy/terraform`](../deploy/terraform) (Cloud Run for api and web, Cloud SQL Postgres 16 with daily backups and point-in-time recovery, Secret Manager, Artifact Registry, and GitHub-to-GCP federation so the pipeline holds no cloud keys). Use one GCP project per environment. Terraform owns the infrastructure; the pipeline owns which image runs (services ignore image drift).

### One-time setup (per environment)

1. **State bucket.** Create a private, versioned GCS bucket for Terraform state (it contains the generated database password).
2. **Infrastructure first.** Copy `deploy/terraform/staging.tfvars.example` to `staging.tfvars` (git-ignored), fill it in, then:

   ```bash
   cd deploy/terraform
   terraform init -backend-config="bucket=<state-bucket>" -backend-config="prefix=helixos/staging"
   terraform apply -var-file=staging.tfvars      # no images set yet: creates everything except the services
   ```

3. **Secrets.** With `ai_provider = "openai"`, add the key (it never passes through Terraform):

   ```bash
   printf '%s' "$OPENAI_KEY" | gcloud secrets versions add helixos-staging-openai-api-key --data-file=- --project <project>
   ```

4. **GitHub environment.** Create environments `staging` and `production` in the repository settings. On `production`, add **required reviewers**. Set each environment's variables from `terraform output github_variables`, plus the public web settings: `OIDC_AUTHORITY`, `OIDC_CLIENT_ID`, `OIDC_AUDIENCE` (and optionally `OIDC_SCOPE`, `OIDC_TOKEN_TYPE`) and `WEB_URL`.
5. **First images.** The services cannot exist before an image does, so run the *Deploy* workflow manually with `images_only` ticked: it builds and pushes both images and deploys nothing. Put those image URLs (`<IMAGE_REPOSITORY>/api:<tag>`, `/web:<tag>`) in `api_image` / `web_image` in your tfvars and `terraform apply` again; that creates the two services. Until then the automatic staging deploy after CI fails with a message saying so. From now on the pipeline deploys.
6. **Identity provider.** Register the web app's callback URL (the site root, e.g. `https://app.example.com/`) and allowed logout URL with the provider; make sure tokens carry `email` and `email_verified` ([modules/auth.md](modules/auth.md)).
7. **First organization.** The API image contains the operator CLI; run it against the environment's database, for example through a one-off Cloud Run job or `gcloud run jobs`, or locally through the Cloud SQL Auth Proxy:

   ```bash
   python -m helixos.auth.admin create-org --id org_acme --name "Acme Labs" --admin-email pi@acme.example
   ```

Production differs from staging in `deploy/terraform` inputs only. Suggested values:

```hcl
environment          = "production"
ai_provider          = "openai"
db_tier              = "db-custom-2-7680"
db_high_availability = true
api_min_instances    = 1
web_min_instances    = 1
web_domain           = "app.example.com"   # managed TLS; verify the domain first
web_url              = "https://app.example.com"
api_url              = "https://api.example.com"
```

Domains are strongly preferable to `run.app` URLs in production because the API URL is compiled into the web image.

### Releasing

- **Staging:** merge to `main`; CI passes; the pipeline builds both images, starts the new API revision with **zero traffic**, waits for `/ready` (which means migrations ran), smoke-tests it at its private candidate URL, and only then shifts traffic; the web follows the same way.
- **Production:** *Run workflow* with `environment: production` and a commit. It refuses commits without a green CI run, then waits for the environment's reviewers.
- **Migrations must be backward compatible.** The previous revision keeps serving against the new schema until promotion (and during a rollback). Add columns and tables in one release; remove or rename them in a later one.
- A failed smoke test leaves the candidate at zero traffic and the old release serving.

### Rolling back

*Run workflow* with the same `environment` and `rollback_to` set to the revision suffix printed in the previous deploy's summary ("To undo it…"). Traffic moves back in seconds; the schema stays at the newer version, which is safe because of the rule above. Rollback targets pipeline releases (they share a suffix across api and web).

### Backups and recovery

Cloud SQL takes a daily backup (14 kept) and keeps 7 days of transaction logs for point-in-time recovery. **A backup you have not restored is not a backup.** Drill it before the beta and after any schema work:

```bash
# Clone to a new instance as of a moment before the incident (the original is untouched)
gcloud sql instances clone helixos-production-pg helixos-restore-test \
  --point-in-time '2026-10-14T03:00:00Z' --project <project>
# Point a throwaway API at the clone, then verify the audit chain end to end
curl -H "Authorization: Bearer <admin token>" "$API/api/v1/audit/verify?organization_id=<org>"
gcloud sql instances delete helixos-restore-test --project <project>
```

### Rotating secrets

Add a new Secret Manager version and deploy a new revision (Cloud Run reads `latest` at revision start). The database password is generated by Terraform; rotate it by tainting `random_password.db` and re-applying, then redeploy the API.

### Known limits of this setup

- **One API instance.** AI sessions and runs are held in process memory; Terraform pins `max_instance_count = 1`. Persist them before scaling out.
- Nothing here has been applied to a live project; the first real `terraform apply` and pipeline run are the actual tests. `terraform validate`, `actionlint`, and the image and smoke-test steps are verified.
- No alerting yet: add uptime checks on `/ready` and error-rate alerts in Cloud Monitoring (tracked in the beta plan).
