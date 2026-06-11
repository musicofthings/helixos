import { app, BrowserWindow, ipcMain, shell } from "electron";
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
import { HELIX_IPC_CHANNELS, type HelixDesktopConfig, type SidecarStatusEvent } from "../shared/desktop-bridge";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

let mainWindow: BrowserWindow | null = null;
let runtimeConfig: DesktopRuntimeConfig | null = null;
let activeApiPort = 8765;
let activeMcpBridgePort = 8766;
let sidecarStatus: SidecarStatusEvent["status"] = "starting";

const mcpHostManager = new McpHostManager();
const mcpBridgeServer = createMcpBridgeServer(mcpHostManager);

function getBridgeConfig(): HelixDesktopConfig {
  const config = runtimeConfig ?? loadDesktopConfig();
  return {
    apiBaseUrl: buildApiBaseUrl(activeApiPort),
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

async function loadWorkspaceWindow(window: BrowserWindow, config: DesktopRuntimeConfig): Promise<void> {
  const target = buildWebLoadTarget(config.webEntry, buildApiBaseUrl(activeApiPort), config.apiToken);
  if (target.file) {
    await window.loadFile(target.file, { query: target.query });
    return;
  }
  if (target.url) {
    await window.loadURL(target.url);
  }
}

async function createMainWindow(): Promise<void> {
  runtimeConfig = loadDesktopConfig();
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
    sidecarEnv: buildSidecarEnvironment(config, buildMcpBridgeUrl(activeMcpBridgePort)),
    onStatus: (status, message) => {
      broadcastSidecarStatus({
        status,
        apiBaseUrl: apiSidecar.apiBaseUrl ?? undefined,
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
}

function registerIpcHandlers(): void {
  ipcMain.handle(HELIX_IPC_CHANNELS.getConfig, () => getBridgeConfig());

  ipcMain.handle(HELIX_IPC_CHANNELS.restartSidecar, async () => {
    if (!runtimeConfig) {
      runtimeConfig = loadDesktopConfig();
    }

    broadcastSidecarStatus({ status: "starting", message: "Restarting sidecar" });
    activeApiPort = await apiSidecar.restart(buildSidecarOptions(runtimeConfig));

    const bridge = getBridgeConfig();
    if (mainWindow) {
      await loadWorkspaceWindow(mainWindow, runtimeConfig);
    }

    return bridge;
  });
}

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

  app.whenReady().then(async () => {
    registerIpcHandlers();
    runtimeConfig = loadDesktopConfig();
    refreshMcpPaths(runtimeConfig);
    await startMcpBridge(runtimeConfig);
    await startSidecar(runtimeConfig);
    setupAutoUpdater();
    await createMainWindow();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      void createMainWindow();
    }
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
  });
}
