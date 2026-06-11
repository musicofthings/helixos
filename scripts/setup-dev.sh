#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> HelixOS dev setup"

mkdir -p .data

if [[ ! -d .venv ]]; then
  echo "Creating Python virtualenv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing API dependencies..."
pip install -U pip wheel
pip install -e "services/api[dev]"

echo "Installing root dev tools..."
npm install

echo "Installing web dependencies..."
npm install --prefix apps/web

echo "Installing desktop dependencies..."
npm install --prefix apps/desktop

if [[ ! -f apps/web/.env.local ]]; then
  cp apps/web/.env.example apps/web/.env.local
  echo "Created apps/web/.env.local from apps/web/.env.example"
fi

echo ""
echo "Setup complete."
echo ""
echo "Start options:"
echo "  npm run dev:browser   # API (8000) + web UI (3000) in the browser"
echo "  npm run dev:desktop     # Electron + sidecar (8765) + web UI (3000)"
echo ""
