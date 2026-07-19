import { contextBridge, ipcRenderer } from "electron";

import {
  HELIX_IPC_CHANNELS,
  HELIX_SIDECAR_STATUS_EVENT,
  type HelixDesktopBridge,
  type SidecarStatusEvent
} from "../shared/desktop-bridge";

let bridgeConfig: HelixDesktopBridge | null = null;
const statusListeners = new Set<(event: SidecarStatusEvent) => void>();

const bridgeState: HelixDesktopBridge = {
  apiBaseUrl: "http://127.0.0.1:8765",
  apiToken: "org-demo-token",
  webBaseUrl: "http://127.0.0.1:3000",
  mcpBridgeUrl: "http://127.0.0.1:8766",
  platform: process.platform,
  sidecarStatus: "starting",
  isDesktop: true
};

function notifySidecarStatus(event: SidecarStatusEvent): void {
  bridgeState.sidecarStatus = event.status;
  if (event.apiBaseUrl) {
    bridgeState.apiBaseUrl = event.apiBaseUrl;
  }

  for (const listener of statusListeners) {
    try {
      listener(event);
    } catch (error) {
      console.error("helixDesktop onSidecarStatus listener failed", error);
    }
  }

  // Also emit a DOM event so non-preload subscribers can react without holding a callback.
  try {
    window.dispatchEvent(new CustomEvent(HELIX_SIDECAR_STATUS_EVENT, { detail: event }));
  } catch {
    // Ignore if the page window is not yet available.
  }
}

async function loadBridgeConfig(): Promise<HelixDesktopBridge> {
  if (bridgeConfig) {
    return bridgeConfig;
  }

  const config = (await ipcRenderer.invoke(HELIX_IPC_CHANNELS.getConfig)) as HelixDesktopBridge;
  bridgeConfig = config;
  Object.assign(bridgeState, config);
  notifySidecarStatus({
    status: config.sidecarStatus,
    apiBaseUrl: config.apiBaseUrl
  });
  return config;
}

void loadBridgeConfig();

ipcRenderer.on(HELIX_IPC_CHANNELS.sidecarStatus, (_event, payload: SidecarStatusEvent) => {
  if (payload.apiBaseUrl) {
    bridgeConfig = bridgeConfig
      ? { ...bridgeConfig, apiBaseUrl: payload.apiBaseUrl, sidecarStatus: payload.status }
      : null;
  } else if (bridgeConfig) {
    bridgeConfig = { ...bridgeConfig, sidecarStatus: payload.status };
  }
  notifySidecarStatus(payload);
});

// contextBridge only reliably supports functions + primitives (not getters).
// Expose live accessors so the renderer always reads current bridgeState.
contextBridge.exposeInMainWorld("helixDesktop", {
  getApiBaseUrl: () => bridgeState.apiBaseUrl,
  getApiToken: () => bridgeState.apiToken,
  getWebBaseUrl: () => bridgeState.webBaseUrl,
  getMcpBridgeUrl: () => bridgeState.mcpBridgeUrl,
  getPlatform: () => bridgeState.platform,
  getSidecarStatus: () => bridgeState.sidecarStatus,
  isDesktop: true as const
});

contextBridge.exposeInMainWorld("helixDesktopActions", {
  restartSidecar: async () => {
    const config = (await ipcRenderer.invoke(
      HELIX_IPC_CHANNELS.restartSidecar
    )) as HelixDesktopBridge;
    bridgeConfig = config;
    Object.assign(bridgeState, config);
    notifySidecarStatus({
      status: config.sidecarStatus,
      apiBaseUrl: config.apiBaseUrl
    });
    return config;
  },
  onSidecarStatus: (listener: (event: SidecarStatusEvent) => void) => {
    statusListeners.add(listener);
    // Immediately sync current status so late subscribers catch up.
    listener({
      status: bridgeState.sidecarStatus,
      apiBaseUrl: bridgeState.apiBaseUrl
    });
    return () => {
      statusListeners.delete(listener);
    };
  }
});
