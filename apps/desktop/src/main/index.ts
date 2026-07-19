import { app, BrowserWindow, ipcMain, shell } from "electron";
import { randomBytes } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildApiBaseUrl,
  buildMcpBridgeUrl,
  buildSidecarEnvironment,
  buildWebLoadTarget,
  loadDesktopConfig,
  type DesktopRuntimeConfig
} from "./config";
import { McpHostManager } from "./mcp/host-manager";
import { createMcpBridgeServer } from "./mcp/bridge-server";
import { apiSidecar } from "./sidecar";
import { setupAutoUpdater } from "./updater";
import { webStaticServer } from "./web-static-server";
import { HELIX_IPC_CHANNELS, type HelixDesktopConfig, type SidecarStatusEvent } from "../shared/desktop-bridge";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

let mainWindow: BrowserWindow | null = null;
let runtimeConfig: DesktopRuntimeConfig | null = null;
let activeApiPort = 8765;
let activeMcpBridgePort = 8766;
let sidecarStatus: SidecarStatusEvent["status"] = "starting";

const mcpBridgeToken = randomBytes(32).toString("hex");
const mcpHostManager = new McpHostManager();
const mcpBridgeServer = createMcpBridgeServer(mcpHostManager, mcpBridgeToken);

function publicApiBaseUrl(): string {
  // Packaged UI is served from an ephemeral loopback port. Prefer the static
  // server origin so renderer fetch stays same-origin via the /api proxy.
  return webStaticServer.baseUrl ?? buildApiBaseUrl(activeApiPort);
}

function getBridgeConfig(): HelixDesktopConfig {
  const config = runtimeConfig ?? loadDesktopConfig();
  return {
    apiBaseUrl: publicApiBaseUrl(),
    apiToken: config.apiToken,
    webBaseUrl: config.webEntry.mode === "url" ? config.webEntry.value : "file://workspace",
    mcpBridgeUrl: buildMcpBridgeUrl(activeMcpBridgePort),
    platform: process.platform,
    sidecarStatus,
    isDesktop: true
  };
}

function broadcastSidecarStatus(event: SidecarStatusEvent): void {
  sidecarStatus = event.status;
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send(HELIX_IPC_CHANNELS.sidecarStatus, event);
  }
}

async function resolveWebEntry(config: DesktopRuntimeConfig): Promise<DesktopRuntimeConfig> {
  // Packaged builds keep the Next export under resources/web. Serve it over
  // loopback HTTP so absolute "/_next/..." CSS/JS URLs work (file:// does not).
  if (config.isPackaged && config.webEntry.mode === "file") {
    const webRoot = path.dirname(config.webEntry.value);
    await webStaticServer.start(webRoot);
    webStaticServer.setApiProxyTarget(buildApiBaseUrl(activeApiPort));
    const baseUrl = webStaticServer.baseUrl;
    if (!baseUrl) {
      throw new Error("Packaged web static server failed to start");
    }
    return {
      ...config,
      webEntry: { mode: "url", value: baseUrl }
    };
  }
  return config;
}

async function loadWorkspaceWindow(window: BrowserWindow, config: DesktopRuntimeConfig): Promise<void> {
  const target = buildWebLoadTarget(config.webEntry, publicApiBaseUrl(), config.apiToken);
  if (target.file) {
    await window.loadFile(target.file, { query: target.query });
    return;
  }
  if (target.url) {
    await window.loadURL(target.url);
  }
}

async function createMainWindow(): Promise<void> {
  runtimeConfig = await resolveWebEntry(loadDesktopConfig());
  refreshMcpPaths(runtimeConfig);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 720,
    title: "HelixOS",
    backgroundColor: "#f7f8f5",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.on("ready-to-show", () => {
    mainWindow?.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  await loadWorkspaceWindow(mainWindow, runtimeConfig);
}

function refreshMcpPaths(config: DesktopRuntimeConfig): void {
  const mcpRoot = config.isPackaged ? path.join(config.resourceRoot, "mcp") : path.join(config.repoRoot, "mcp");
  mcpHostManager.register({
    id: "biopython-local",
    binaryPath: config.mcpBiopythonBinary,
    scriptPath: config.mcpBiopythonBinary
      ? undefined
      : path.join(mcpRoot, "servers/biopython_local/server.py"),
    pythonExecutable: config.pythonExecutable
  });
}

function buildSidecarOptions(config: DesktopRuntimeConfig): Parameters<typeof apiSidecar.start>[0] {
  return {
    apiDir: config.apiDir,
    apiBinary: config.apiBinary,
    preferredPort: config.apiPort,
    pythonExecutable: config.pythonExecutable,
    mcpBridgeUrl: buildMcpBridgeUrl(activeMcpBridgePort),
    mcpBridgeToken,
    sidecarEnv: buildSidecarEnvironment(config, buildMcpBridgeUrl(activeMcpBridgePort)),
    onStatus: (status, message) => {
      if (apiSidecar.apiBaseUrl) {
        webStaticServer.setApiProxyTarget(apiSidecar.apiBaseUrl);
      }
      broadcastSidecarStatus({
        status,
        apiBaseUrl: publicApiBaseUrl(),
        message
      });
    },
    onLog: (line) => {
      if (line) {
        console.log(`[helix-api] ${line}`);
      }
    }
  };
}

async function startMcpBridge(config: DesktopRuntimeConfig): Promise<number> {
  await mcpHostManager.startAll();
  activeMcpBridgePort = await mcpBridgeServer.start(config.mcpBridgePort);
  return activeMcpBridgePort;
}

async function startSidecar(config: DesktopRuntimeConfig): Promise<void> {
  activeApiPort = await apiSidecar.start(buildSidecarOptions(config));
  webStaticServer.setApiProxyTarget(buildApiBaseUrl(activeApiPort));
}

function registerIpcHandlers(): void {
  ipcMain.handle(HELIX_IPC_CHANNELS.getConfig, () => getBridgeConfig());

  ipcMain.handle(HELIX_IPC_CHANNELS.restartSidecar, async () => {
    if (!runtimeConfig) {
      runtimeConfig = loadDesktopConfig();
    }

    broadcastSidecarStatus({ status: "starting", message: "Restarting sidecar" });
    activeApiPort = await apiSidecar.restart(buildSidecarOptions(runtimeConfig));

    runtimeConfig = await resolveWebEntry(runtimeConfig);
    const bridge = getBridgeConfig();
    if (mainWindow) {
      await loadWorkspaceWindow(mainWindow, runtimeConfig);
    }

    return bridge;
  });
}

/** Resolves once the first whenReady boot finishes (sidecar + first window). */
let bootReady: Promise<void> | null = null;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore();
      }
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    bootReady = (async () => {
      registerIpcHandlers();
      runtimeConfig = await resolveWebEntry(loadDesktopConfig());
      refreshMcpPaths(runtimeConfig);
      await startMcpBridge(runtimeConfig);
      await startSidecar(runtimeConfig);
      setupAutoUpdater();
      await createMainWindow();
    })();
    return bootReady;
  });

  app.on("activate", () => {
    void (async () => {
      // Wait for initial boot so activate cannot open a window against an
      // unbound sidecar / half-started static server.
      if (bootReady) {
        await bootReady;
      }
      if (BrowserWindow.getAllWindows().length === 0) {
        await createMainWindow();
      }
    })();
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("before-quit", () => {
    void apiSidecar.stop();
    void mcpBridgeServer.stop();
    void mcpHostManager.stopAll();
    void webStaticServer.stop();
  });
}
