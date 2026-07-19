export type SidecarStatus = "starting" | "ready" | "error" | "stopped";

/**
 * Desktop bridge exposed via contextBridge. Config fields are function
 * accessors so reads stay live (Electron does not support property getters).
 */
export type HelixDesktopBridge = {
  getApiBaseUrl: () => string;
  getApiToken: () => string;
  getWebBaseUrl: () => string;
  getMcpBridgeUrl: () => string;
  getPlatform: () => string;
  getSidecarStatus: () => SidecarStatus;
  isDesktop: true;
};

export type SidecarStatusEvent = {
  status: SidecarStatus;
  apiBaseUrl?: string;
  message?: string;
};

export type HelixDesktopActions = {
  restartSidecar: () => Promise<{
    apiBaseUrl: string;
    apiToken: string;
    webBaseUrl: string;
    mcpBridgeUrl: string;
    platform: string;
    sidecarStatus: SidecarStatus;
    isDesktop: true;
  }>;
  onSidecarStatus?: (listener: (event: SidecarStatusEvent) => void) => () => void;
};

declare global {
  interface Window {
    helixDesktop?: HelixDesktopBridge;
    helixDesktopActions?: HelixDesktopActions;
  }

  interface WindowEventMap {
    "helix:sidecar-status-changed": CustomEvent<SidecarStatusEvent>;
  }
}

export {};
