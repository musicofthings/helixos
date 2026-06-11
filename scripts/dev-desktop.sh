#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run npm run setup first."
  exit 1
fi

# Free ports used by a prior browser or desktop session.
for port in 3000 8765 8766; do
  lsof -ti ":${port}" 2>/dev/null | xargs kill -9 2>/dev/null || true
done

export HELIX_DISABLE_AUTOUPDATE=1
export HELIX_PYTHON="${HELIX_PYTHON:-${ROOT}/.venv/bin/python3}"
export HELIX_WEB_URL="${HELIX_WEB_URL:-http://127.0.0.1:3000}"

# Cursor/CI sometimes sets this, which prevents Electron from bootstrapping its APIs.
unset ELECTRON_RUN_AS_NODE

cd apps/desktop
exec npm run dev:stack
