import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { app } from "electron";

const DEFAULT_API_PORT = 8765;
const DEFAULT_MCP_BRIDGE_PORT = 8766;
const DEFAULT_WEB_URL = "http://127.0.0.1:3000";
const DEFAULT_API_TOKEN = "org-demo-token";

export type DesktopRuntimeConfig = {
  repoRoot: string;
  resourceRoot: string;
  bundledRoot: string;
  apiDir: string;
  apiBinary?: string;
  mcpBiopythonBinary?: string;
  webEntry: WebEntry;
  apiPort: number;
  mcpBridgePort: number;
  apiToken: string;
  pythonExecutable: string;
  databaseUrl: string;
  isPackaged: boolean;
};

export type WebEntry =
  | { mode: "url"; value: string }
  | { mode: "file"; value: string };

export function resolveRepoRoot(): string {
  if (process.env.HELIXOS_ROOT) {
    return path.resolve(process.env.HELIXOS_ROOT);
  }

  const currentDir = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(currentDir, "../../../..");
}

export function resolveBundledBinary(bundledRoot: string, binaryName: string): string | undefined {
  const extension = process.platform === "win32" ? ".exe" : "";
  const candidate = path.join(bundledRoot, "bin", `${binaryName}${extension}`);
  return existsSync(candidate) ? candidate : undefined;
}

function resolveBundledPython(bundledRoot: string): string | undefined {
  const venvPython =
    process.platform === "win32"
      ? path.join(bundledRoot, "pyvenv/Scripts/python.exe")
      : path.join(bundledRoot, "pyvenv/bin/python3");
  if (existsSync(venvPython)) {
    return venvPython;
  }

  const embeddedPython =
    process.platform === "win32"
      ? path.join(bundledRoot, "python/python.exe")
      : path.join(bundledRoot, "python/bin/python3");
  return existsSync(embeddedPython) ? embeddedPython : undefined;
}

export function resolveDesktopDatabaseUrl(isPackaged: boolean, repoRoot?: string): string {
  if (process.env.HELIX_DATABASE_URL) {
    return process.env.HELIX_DATABASE_URL;
  }

  if (!isPackaged && repoRoot) {
    const dbDir = path.join(repoRoot, ".data");
    mkdirSync(dbDir, { recursive: true });
    return `sqlite:///${path.join(dbDir, "helixos-dev.db")}`;
  }

  if (!isPackaged) {
    return "";
  }

  const dbDir = path.join(app.getPath("userData"), "helixos");
  mkdirSync(dbDir, { recursive: true });
  const dbPath = path.join(dbDir, "helixos.db");
  return `sqlite:///${dbPath}`;
}

export function loadDesktopConfig(): DesktopRuntimeConfig {
  const isPackaged = app.isPackaged;
  const repoRoot = resolveRepoRoot();
  const resourceRoot = isPackaged ? process.resourcesPath : repoRoot;
  const bundledRoot = isPackaged ? resourceRoot : path.join(repoRoot, "apps/desktop/resources");
  const bundledPython = resolveBundledPython(bundledRoot);

  return {
    repoRoot,
    resourceRoot,
    bundledRoot,
    apiDir: isPackaged ? path.join(resourceRoot, "api") : path.join(repoRoot, "services/api"),
    apiBinary: resolveBundledBinary(bundledRoot, "helixos-api"),
    mcpBiopythonBinary: resolveBundledBinary(bundledRoot, "helixos-mcp-biopython"),
    webEntry: isPackaged
      ? { mode: "file", value: path.join(resourceRoot, "web/index.html") }
      : { mode: "url", value: process.env.HELIX_WEB_URL ?? DEFAULT_WEB_URL },
    apiPort: Number(process.env.HELIX_API_PORT ?? DEFAULT_API_PORT),
    mcpBridgePort: Number(process.env.HELIX_MCP_BRIDGE_PORT ?? DEFAULT_MCP_BRIDGE_PORT),
    apiToken: process.env.HELIX_API_TOKEN ?? DEFAULT_API_TOKEN,
    pythonExecutable: bundledPython ?? process.env.HELIX_PYTHON ?? "python3",
    databaseUrl: resolveDesktopDatabaseUrl(isPackaged, repoRoot),
    isPackaged
  };
}

export function buildApiBaseUrl(port: number): string {
  return `http://127.0.0.1:${port}`;
}

export function buildMcpBridgeUrl(port: number): string {
  return `http://127.0.0.1:${port}`;
}

export type WebLoadTarget = {
  url?: string;
  file?: string;
  query: Record<string, string>;
};

export function buildWebLoadTarget(
  webEntry: WebEntry,
  apiBaseUrl: string,
  apiToken: string
): WebLoadTarget {
  const query = {
    helix_api: apiBaseUrl,
    helix_token: apiToken,
    helix_desktop: "1"
  };

  if (webEntry.mode === "file") {
    return { file: webEntry.value, query };
  }

  const url = new URL(webEntry.value);
  for (const [key, value] of Object.entries(query)) {
    url.searchParams.set(key, value);
  }
  return { url: url.toString(), query };
}

export function buildSidecarEnvironment(config: DesktopRuntimeConfig, mcpBridgeUrl: string) {
  return {
    ...process.env,
    HELIX_MCP_BRIDGE_URL: mcpBridgeUrl,
    ...(config.databaseUrl ? { HELIX_DATABASE_URL: config.databaseUrl } : {})
  };
}
