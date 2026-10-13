#!/usr/bin/env bash
# Run one piece of the local OIDC stack: mock | api | web
#   mock  mock identity provider on :9100
#   api   API on :8000 verifying its tokens (fresh DB; first user becomes admin of org_acme)
#   web   Next dev server on :3000 signing in against it
# Usage: bash scripts/dev-oidc.sh mock   (then api, then web, in separate terminals)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

IDP_PORT="${IDP_PORT:-9100}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@acme.test}"

case "${1:-}" in
  mock)
    exec python services/api/scripts/mock_oidc.py --port "$IDP_PORT"
    ;;
  api)
    mkdir -p .data
    export HELIX_DATABASE_URL="${HELIX_DATABASE_URL:-sqlite:///${ROOT}/.data/helixos-oidc.db}"
    export HELIX_OIDC_ISSUER="http://localhost:${IDP_PORT}"
    export HELIX_OIDC_AUDIENCE="helixos-api"
    cd services/api
    python -m helixos.auth.admin create-org --id org_acme --name "Acme Labs" \
      --admin-email "$ADMIN_EMAIL" >/dev/null 2>&1 || true
    echo "API on http://127.0.0.1:8000; ${ADMIN_EMAIL} is admin of org_acme"
    exec python -m uvicorn helixos.main:app --host 127.0.0.1 --port 8000 --reload
    ;;
  web)
    cd apps/web
    # Empty API URL = same-origin /api through the Next proxy.
    export NEXT_PUBLIC_API_URL=""
    export NEXT_PUBLIC_API_TOKEN=""
    export NEXT_PUBLIC_OIDC_AUTHORITY="http://localhost:${IDP_PORT}"
    export NEXT_PUBLIC_OIDC_CLIENT_ID="helixos-web"
    export NEXT_PUBLIC_OIDC_AUDIENCE="helixos-api"
    exec npx next dev -p 3000
    ;;
  *)
    echo "usage: bash scripts/dev-oidc.sh mock|api|web" >&2
    exit 2
    ;;
esac
