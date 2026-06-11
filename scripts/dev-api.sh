#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run npm run setup first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

mkdir -p .data
export HELIX_DATABASE_URL="${HELIX_DATABASE_URL:-sqlite:///${ROOT}/.data/helixos-dev.db}"
export HELIX_AI_PROVIDER="${HELIX_AI_PROVIDER:-stub}"
export HELIX_DISABLE_AUTOUPDATE="${HELIX_DISABLE_AUTOUPDATE:-1}"

cd services/api
echo "Starting HelixOS API on http://127.0.0.1:8000"
echo "Database: ${HELIX_DATABASE_URL}"
exec python -m uvicorn helixos.main:app --host 127.0.0.1 --port 8000 --reload
