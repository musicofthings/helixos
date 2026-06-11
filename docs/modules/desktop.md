# Desktop Shell

The desktop app wraps the HelixOS web workspace in Electron, starts a local FastAPI sidecar, and hosts stdio MCP connectors through a local bridge.

**Related:** [mcp.md](mcp.md) · [audit.md](audit.md) · [auth.md](auth.md) · [SYSTEM_ARCHITECTURE.md](../../SYSTEM_ARCHITECTURE.md)

## Role in the Platform

Desktop is required for **stdio MCP connector jobs** (BioPython Local). Browser-only dev can use ELN, sequences, AI, and audit — but not `POST /api/v1/mcp/jobs` without a bridge.

```txt
Electron main  →  spawns API sidecar (:8765) + MCP bridge (:8766)
              →  loads apps/web with helix_api + helix_token
Web workspace →  api-client → sidecar
MCP jobs      →  sidecar → HELIX_MCP_BRIDGE_URL → stdio server
Audit           →  SQLite via HELIX_DATABASE_URL (see audit.md)
```

## Architecture

- `apps/desktop/src/main`: Electron main process, window lifecycle, API sidecar spawn, MCP bridge.
- `apps/desktop/src/preload`: Secure bridge exposing `window.helixDesktop`.
- `apps/web`: Loaded from the Next.js dev server in development or a static export in packaged builds.

Runtime services:

```bash
python3 -m uvicorn helixos.main:app --host 127.0.0.1 --port <api-port>
python3 mcp/servers/biopython_local/server.py   # stdio connector host
http://127.0.0.1:<bridge-port>                    # MCP bridge for API dispatch
```

The renderer receives runtime config through:

- `window.helixDesktop` from preload
- `?helix_api=` / `?helix_token=` query params as a first-paint fallback (avoids hydration mismatch)

## Development

From repo root (recommended):

```bash
npm run dev:desktop
```

Or manually:

```bash
pip install -e services/api[dev]
cd apps/desktop
npm install
npm run dev:stack
```

Unset `ELECTRON_RUN_AS_NODE` if your IDE sets it — that breaks Electron APIs.

## Production Packaging

```bash
pip install -e 'services/api[desktop]'
cd apps/desktop
npm run pack
```

The prepare step attempts to build PyInstaller binaries:

- `helixos-api`
- `helixos-mcp-biopython`

When present, packaged builds use bundled executables instead of system Python. If PyInstaller is unavailable, the app falls back to source Python under `resources/api`.

Build binaries manually:

```bash
pip install -e 'services/api[desktop]'
python3 services/api/scripts/build_desktop_binaries.py
python3 services/api/scripts/fetch_embedded_python.py
python3 services/api/scripts/bootstrap_embedded_python_env.py
```

Packaged apps prefer this order:

1. PyInstaller sidecar binaries (`helixos-api`, `helixos-mcp-biopython`)
2. Embedded Python venv at `resources/pyvenv`
3. Embedded Python runtime at `resources/python`

Desktop audit data persists to SQLite at `<userData>/helixos/helixos.db` unless `HELIX_DATABASE_URL` is overridden. See [audit.md](audit.md).

## Auto-update And Code Signing

Packaged builds include `electron-updater` and check `https://releases.helixos.example/desktop` for updates on launch.

Environment controls:

| Variable | Purpose |
| --- | --- |
| `HELIX_DISABLE_AUTOUPDATE=1` | Disable update checks |
| `CSC_LINK` / `CSC_KEY_PASSWORD` | Windows/macOS signing certificate |
| `APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD` | macOS notarization credentials |

macOS builds use `build/entitlements.mac.plist` for hardened runtime compatibility with Electron and bundled Python sidecars.

## Environment Overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `HELIXOS_ROOT` | auto-detected | Monorepo root for dev sidecar and MCP scripts |
| `HELIX_API_PORT` | `8765` | Preferred API sidecar port |
| `HELIX_MCP_BRIDGE_PORT` | `8766` | Preferred MCP bridge port |
| `HELIX_WEB_URL` | `http://127.0.0.1:3000` | Dev web workspace URL |
| `HELIX_API_TOKEN` | `org-demo-token` | Bearer token injected into the shell |
| `HELIX_PYTHON` | `python3` | Python executable for sidecar and MCP servers |

## IPC Surface

- `window.helixDesktop`: runtime config, sidecar status, MCP bridge URL
- `window.helixDesktopActions.restartSidecar()`: restart the API sidecar and reload the window

## Command Palette

The workspace exposes a Warp-style command palette with `⌘K` / `Ctrl+K` for navigation, connector jobs, and desktop actions.

## Audit And Security

- Renderer runs with context isolation and no Node integration.
- External links open in the system browser.
- Sidecar and MCP bridge bind to `127.0.0.1` only.

## Troubleshooting

### JavaScript error on launch

If you see `Cannot read properties of undefined (reading 'exports')` or `requestSingleInstanceLock`, the desktop shell was likely built as ESM while loading CommonJS-only dependencies such as `electron-updater`.

The desktop app builds the main and preload processes as CommonJS (`.cjs`). Rebuild and relaunch:

```bash
cd apps/desktop
npm run build
npm run dev:stack
```

If launching from a terminal that sets `ELECTRON_RUN_AS_NODE=1` (some IDE integrations do this), unset it first:

```bash
unset ELECTRON_RUN_AS_NODE
npm run dev:desktop
```

Stop any browser-only dev server on port 3000 before starting the desktop stack, or run `npm run dev:desktop` which clears ports 3000/8765/8766 automatically.

## Remaining Work

- Production release URL for auto-update (currently placeholder domain)
- Full `npm run pack` CI pipeline with embedded Python download on all platforms
- Static export path for packaged web bundle (dev loads Next.js server today)
