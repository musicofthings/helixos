export type SidecarStatus = "starting" | "ready" | "error" | "stopped";

export type HelixDesktopBridge = {
  apiBaseUrl: string;
  apiToken: string;
  webBaseUrl: string;
  mcpBridgeUrl: string;
  platform: string;
  sidecarStatus: SidecarStatus;
  isDesktop: true;
};

export type SidecarStatusEvent = {
  status: SidecarStatus;
  apiBaseUrl?: string;
  message?: string;
};

export type HelixDesktopActions = {
  restartSidecar: () => Promise<HelixDesktopBridge>;
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
