import { contextBridge, ipcRenderer } from "electron";

import {
  HELIX_IPC_CHANNELS,
  type HelixDesktopBridge,
  type SidecarStatusEvent
} from "../shared/desktop-bridge";

let bridgeConfig: HelixDesktopBridge | null = null;

async function loadBridgeConfig(): Promise<HelixDesktopBridge> {
  if (bridgeConfig) {
    return bridgeConfig;
  }

  const config = await ipcRenderer.invoke(HELIX_IPC_CHANNELS.getConfig);
  bridgeConfig = config;
  return config;
}

const bridge: HelixDesktopBridge = {
  apiBaseUrl: "http://127.0.0.1:8765",
  apiToken: "org-demo-token",
  webBaseUrl: "http://127.0.0.1:3000",
  mcpBridgeUrl: "http://127.0.0.1:8766",
  platform: process.platform,
  sidecarStatus: "starting",
  isDesktop: true
};

void loadBridgeConfig().then((config) => {
  Object.assign(bridge, config);
});

ipcRenderer.on(HELIX_IPC_CHANNELS.sidecarStatus, (_event, payload: SidecarStatusEvent) => {
  bridge.sidecarStatus = payload.status;
  if (payload.apiBaseUrl) {
    bridge.apiBaseUrl = payload.apiBaseUrl;
  }
});

contextBridge.exposeInMainWorld("helixDesktop", bridge);

contextBridge.exposeInMainWorld("helixDesktopActions", {
  restartSidecar: () => ipcRenderer.invoke(HELIX_IPC_CHANNELS.restartSidecar)
});
